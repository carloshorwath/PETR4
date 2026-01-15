import re
import json
import unicodedata
import logging
from datetime import datetime
from pathlib import Path
from config import Config

# Helper function to avoid circular import if media imports utils (it doesn't, but safe practice)
# But here we need get_audio_duration.
# If I import it at top level, and media doesn't import utils, it's fine.
try:
    from media import get_audio_duration
except ImportError:
    # Fallback or dummy if media not found (e.g. running tests without proper path)
    def get_audio_duration(path): return 0.0

def clean_text_for_search(text: str) -> str:
    """
    Normalizes text for search comparisons: lowercase, remove accents, remove punctuation.
    """
    if not text:
        return ""
    # Normalize to NFD form to separate accents
    text = unicodedata.normalize('NFD', text)
    # Remove accents
    text = "".join(c for c in text if unicodedata.category(c) != 'Mn')
    # Lowercase
    text = text.lower()
    # Remove punctuation and special characters
    text = re.sub(r"[.,!?;:\[\]*\"“”‘’—–-]", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def clean_script_initial(raw_script: str):
    """
    Cleans the raw script from the LLM.
    Returns:
        roteiro_limpo: Script without markers (for TTS).
        roteiro_com_marcadores: Script with markers (for segmentation).
    """
    # Remove external quotes if present
    script = re.sub(r'^"(.*)"$', r'\1', raw_script)
    # Normalize newlines and spaces
    script = re.sub(r'[\r\n]+', ' ', script)
    script = re.sub(r'\s\s+', ' ', script)
    script = script.strip()

    roteiro_com_marcadores = script
    # Remove marker for the clean version
    roteiro_limpo = script.replace("[TROCAR_IMAGEM]", " ")

    return roteiro_limpo, roteiro_com_marcadores

def segment_script_with_markers(roteiro_com_marcadores: str) -> list:
    """
    Splits the script into segments based on [TROCAR_IMAGEM].
    Returns a list of clean text segments.
    """
    segments = roteiro_com_marcadores.split('[TROCAR_IMAGEM]')
    cleaned_segments = []

    for segment in segments:
        text = segment.strip()
        if not text:
            # Fallback for empty segment (end of script sometimes)
            text = "Crie uma cena de encerramento simbólica que capture o tema principal da história: redenção, perdão e a providência divina."
        cleaned_segments.append(text)

    return cleaned_segments

def srt_time_to_seconds(time_str: str) -> float:
    """Converts '00:00:00,000' to seconds."""
    if not time_str:
        return 0.0
    parts = re.split(r'[:,]', time_str)
    if len(parts) != 4:
        return 0.0

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2])
    milliseconds = int(parts[3])

    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0

def parse_srt(srt_content: str) -> list:
    """
    Parses SRT content string into a list of dicts:
    [{'number': 1, 'startTime': 0.0, 'endTime': 1.5, 'text': '...'}]
    """
    # Remove BOM if present
    srt_content = srt_content.lstrip('\ufeff').strip()
    if not srt_content:
        return []

    lines = re.split(r'\r?\n', srt_content)
    subtitles = []
    current_subtitle = {}

    for line in lines:
        line = line.strip()
        if not line:
            if current_subtitle:
                subtitles.append(current_subtitle)
                current_subtitle = {}
        elif 'number' not in current_subtitle and line.isdigit():
            current_subtitle['number'] = int(line)
        elif 'startTime' not in current_subtitle and '-->' in line:
            times = line.split(' --> ')
            if len(times) == 2:
                current_subtitle['startTime'] = srt_time_to_seconds(times[0])
                current_subtitle['endTime'] = srt_time_to_seconds(times[1])
                current_subtitle['duration'] = current_subtitle['endTime'] - current_subtitle['startTime']
        else:
            current_text = current_subtitle.get('text', '')
            current_subtitle['text'] = (current_text + " " + line).strip()

    if current_subtitle:
        subtitles.append(current_subtitle)

    return subtitles

def calculate_image_durations(segments: list, subtitles: list, total_audio_duration: float) -> list:
    """
    Matches script segments to subtitles with ROBUST FALLBACK.
    """
    tempos_de_transicao = [0.0]
    ultimo_indice_srt = 0

    for i in range(1, len(segments)):
        segmento_atual = segments[i]
        if not segmento_atual:
            continue

        # TENTATIVA 1: Âncora de 3 palavras
        words = segmento_atual.split()
        ancora_3 = clean_text_for_search(" ".join(words[:3]))

        transicao_encontrada = False

        for j in range(ultimo_indice_srt, len(subtitles)):
            texto_janela = clean_text_for_search(subtitles[j].get('text', ''))
            if j + 1 < len(subtitles):
                texto_janela += " " + clean_text_for_search(subtitles[j+1].get('text', ''))

            if ancora_3 in texto_janela:
                tempos_de_transicao.append(subtitles[j]['startTime'])
                ultimo_indice_srt = j
                transicao_encontrada = True
                break

        # FALLBACK 1: Tentar com 2 palavras
        if not transicao_encontrada and len(words) >= 2:
            ancora_2 = clean_text_for_search(" ".join(words[:2]))
            for j in range(ultimo_indice_srt, len(subtitles)):
                texto_janela = clean_text_for_search(subtitles[j].get('text', ''))
                if j + 1 < len(subtitles):
                    texto_janela += " " + clean_text_for_search(subtitles[j+1].get('text', ''))

                if ancora_2 in texto_janela:
                    tempos_de_transicao.append(subtitles[j]['startTime'])
                    ultimo_indice_srt = j
                    transicao_encontrada = True
                    print(f"⚠️ Fallback 2-word anchor used for segment {i+1}")
                    break

        # FALLBACK 2: Interpolação linear
        if not transicao_encontrada:
            print(f"⚠️ Sync failed for segment {i+1}. Using interpolation.")
            # Distribui o tempo restante igualmente entre os segmentos faltantes
            segmentos_restantes = len(segments) - i
            tempo_restante = total_audio_duration - tempos_de_transicao[-1]
            tempo_interpolado = tempos_de_transicao[-1] + (tempo_restante / segmentos_restantes)
            tempos_de_transicao.append(tempo_interpolado)

    tempos_de_transicao.append(total_audio_duration)

    duracoes = []
    for i in range(len(tempos_de_transicao) - 1):
        duracao_cena = tempos_de_transicao[i+1] - tempos_de_transicao[i]
        duracoes.append(max(0.1, round(duracao_cena, 3)))

    if len(segments) != len(duracoes):
        raise ValueError(f"Erro de contagem: {len(segments)} segmentos vs {len(duracoes)} durações calculadas.")

    resultado = []
    for index, duration in enumerate(duracoes):
        resultado.append({
            "image": f"image_{index + 1}",
            "duration": duration,
            "text_segment": segments[index]
        })

    return resultado

def parse_json_transcription(json_content: str) -> list:
    """
    Lê o JSON de transcrição (formato Whisper/Word-Level) e retorna a lista de palavras.
    """
    try:
        data = json.loads(json_content)
        if "words" in data:
            return data["words"]
        elif isinstance(data, list):
            return data
        else:
            return []
    except json.JSONDecodeError:
        return []

def calculate_durations_from_words(segments: list, word_data: list, total_audio_duration: float) -> list:
    """
    Calcula durações baseado no timestamp exato das palavras (JSON),
    em vez de estimar por janelas de tempo (SRT).
    """
    tempos_de_transicao = [0.0]
    current_word_idx = 0

    for i in range(1, len(segments)):
        segmento_texto = segments[i]
        if not segmento_texto:
            continue

        words_script = segmento_texto.split()
        ancora_limpa = clean_text_for_search(" ".join(words_script[:3]))

        match_found = False

        for j in range(current_word_idx, len(word_data) - 2):
            palavra_1 = word_data[j].get('word', '')
            palavra_2 = word_data[j+1].get('word', '')
            palavra_3 = word_data[j+2].get('word', '')

            texto_json = clean_text_for_search(f"{palavra_1} {palavra_2} {palavra_3}")

            if ancora_limpa in texto_json:
                start_time = word_data[j]['start']
                tempos_de_transicao.append(start_time)
                current_word_idx = j + 1
                match_found = True
                break

        if not match_found:
            print(f"AVISO: Sincronia exata não encontrada para o segmento: '{ancora_limpa}...'")
            tempos_de_transicao.append(tempos_de_transicao[-1])

    tempos_de_transicao.append(total_audio_duration)

    duracoes = []
    for i in range(len(tempos_de_transicao) - 1):
        duracao_cena = tempos_de_transicao[i+1] - tempos_de_transicao[i]
        duracoes.append(max(0.1, round(duracao_cena, 3)))

    resultado = []
    for index, duration in enumerate(duracoes):
        resultado.append({
            "image": f"image_{index + 1}",
            "duration": duration,
            "text_segment": segments[index]
        })

    return resultado

def setup_logger(project_slug: str) -> logging.Logger:
    """Configura logger para o projeto"""
    log_dir = Config.get_project_dir(project_slug) / "logs"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger(f"bible_video_{project_slug}")
    logger.setLevel(logging.DEBUG)

    # Check if handlers already exist to avoid duplication
    if not logger.handlers:
        # Handler para arquivo
        fh = logging.FileHandler(
            log_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        fh.setLevel(logging.DEBUG)

        # Handler para console
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formato
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger

def validate_image_file(image_path: Path) -> bool:
    """Valida se a imagem é legível"""
    if not image_path.exists():
        return False
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            img.verify()  # Verifica integridade
        return True
    except Exception as e:
        print(f"Imagem corrompida: {image_path} - {e}")
        return False

def validate_audio_file(audio_path: Path) -> bool:
    """Valida se o áudio é legível"""
    if not audio_path.exists():
        return False
    try:
        duration = get_audio_duration(audio_path)
        return duration > 0
    except Exception as e:
        print(f"Áudio corrompido: {audio_path} - {e}")
        return False
