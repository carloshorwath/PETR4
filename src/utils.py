import re
import json
import unicodedata

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
    Matches script segments to subtitles to calculate display duration for each image.
    Returns a list of dicts: [{'image': 'image_1', 'duration': 5.0}, ...]
    """
    tempos_de_transicao = [0.0]
    ultimo_indice_srt = 0

    # We skip the first segment for transition search because it starts at 0.0
    # The logic searches for the START of the NEXT segment to determine the END of the CURRENT one.
    # Wait, the JS logic iterates from i=1.
    # segments[0] is the first scene.
    # segments[1] starts the second scene. finding its start time gives us the end of scene 1.

    for i in range(1, len(segments)):
        segmento_atual = segments[i]
        if not segmento_atual:
            continue

        # Anchor: first 3 words
        words = segmento_atual.split()
        ancora = clean_text_for_search(" ".join(words[:3]))

        transicao_encontrada = False

        for j in range(ultimo_indice_srt, len(subtitles)):
            texto_janela = clean_text_for_search(subtitles[j].get('text', ''))

            # Check next line as well (window)
            if j + 1 < len(subtitles):
                texto_janela += " " + clean_text_for_search(subtitles[j+1].get('text', ''))

            if ancora in texto_janela:
                tempos_de_transicao.append(subtitles[j]['startTime'])
                ultimo_indice_srt = j
                transicao_encontrada = True
                break

        if not transicao_encontrada:
            # Log warning but continue? Or throw error as per JS?
            # JS throws error. Let's print for now to debug in streamlit.
            print(f"WARNING: Sync failed for segment {i+1} anchor '{ancora}'.")
            # Fallback: distribute remaining time equally?
            # For now, let's just append the previous time + small buffer or handle it gracefully?
            # The JS throws an error. I'll raise one too to catch it in UI.
            raise ValueError(f"SINCRONIA FALHOU: Não foi possível encontrar a âncora do segmento {i + 1} ('{ancora}...') no arquivo SRT.")

    # Add total duration as the end of the last segment
    tempos_de_transicao.append(total_audio_duration)

    duracoes = []
    for i in range(len(tempos_de_transicao) - 1):
        duracao_cena = tempos_de_transicao[i+1] - tempos_de_transicao[i]
        duracoes.append(max(0.1, round(duracao_cena, 3)))

    # Validation
    if len(segments) != len(duracoes):
        raise ValueError(f"Erro de contagem: {len(segments)} segmentos vs {len(duracoes)} durações calculadas.")

    resultado = []
    for index, duration in enumerate(duracoes):
        resultado.append({
            "image": f"image_{index + 1}",
            "duration": duration,
            "text_segment": segments[index] # storing text too for reference
        })

    return resultado

def parse_json_transcription(json_content: str) -> list:
    """
    Lê o JSON de transcrição (formato Whisper/Word-Level) e retorna a lista de palavras.
    """
    try:
        data = json.loads(json_content)
        # Tenta pegar a chave 'words' (padrão do seu arquivo hook_transcription.json)
        if "words" in data:
            return data["words"]
        # Fallback: se for uma lista direta ou outro formato
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

    # Índice para não buscar palavras que já passaram
    current_word_idx = 0

    # Pula o primeiro segmento (pois ele começa em 0.0)
    for i in range(1, len(segments)):
        segmento_texto = segments[i]
        if not segmento_texto:
            continue

        # Pega as 3 primeiras palavras do roteiro como âncora
        words_script = segmento_texto.split()
        # Normaliza (remove acentos/pontuação) para bater com o JSON
        ancora_limpa = clean_text_for_search(" ".join(words_script[:3]))

        match_found = False

        # Procura essa sequência de palavras na lista do JSON
        for j in range(current_word_idx, len(word_data) - 2): # -2 para garantir janela de 3
            # Monta uma janela de 3 palavras do JSON para comparar
            palavra_1 = word_data[j].get('word', '')
            palavra_2 = word_data[j+1].get('word', '')
            palavra_3 = word_data[j+2].get('word', '')

            texto_json = clean_text_for_search(f"{palavra_1} {palavra_2} {palavra_3}")

            # Se a âncora do roteiro estiver dentro da sequência do JSON
            if ancora_limpa in texto_json:
                # O tempo de corte é o 'start' da primeira palavra encontrada
                start_time = word_data[j]['start']
                tempos_de_transicao.append(start_time)

                # Atualiza o índice para a próxima busca começar daqui
                current_word_idx = j + 1
                match_found = True
                break

        if not match_found:
            print(f"AVISO: Sincronia exata não encontrada para o segmento: '{ancora_limpa}...'")
            # Fallback: Mantém o tempo anterior (ou poderia interpolar)
            tempos_de_transicao.append(tempos_de_transicao[-1])

    tempos_de_transicao.append(total_audio_duration)

    # Calcula a duração de cada cena (Next Start - Current Start)
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
