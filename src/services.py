import json
import requests
from pathlib import Path
from config import Config

TIMEOUT_SECONDS = 120  # 2 minutes

class LLMService:
    def generate_script(self, story_topic: str, images_count: int) -> str:
        # 1. Try n8n Webhook
        if Config.N8N_SCRIPT_WEBHOOK_URL:
            try:
                payload = {
                    "topic": story_topic,
                    "imageCount": images_count
                }
                response = requests.post(Config.N8N_SCRIPT_WEBHOOK_URL, json=payload, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                data = response.json()

                if "script" in data:
                    return data["script"]
                if isinstance(data, list) and len(data) > 0 and "script" in data[0]:
                    return data[0]["script"]
                return response.text
            except requests.Timeout:
                 print(f"Script Webhook timed out.")
            except Exception as e:
                print(f"Script Webhook failed: {e}. Trying fallback...")

        # 2. Fallback: Direct API (OpenRouter/OpenAI compatible) via requests
        if not Config.OPENROUTER_API_KEY:
             raise ValueError("Neither N8N_SCRIPT_WEBHOOK_URL nor OPENROUTER_API_KEY is configured.")

        prompt = f"""Reconte a história bíblica de **{story_topic}**.

**TAREFA PRINCIPAL:**
Enquanto escreve o roteiro, você deve inserir o marcador **[TROCAR_IMAGEM]** exatamente **{images_count - 1}** vezes no texto. Posicione este marcador nos pontos de virada da narrativa, onde uma mudança de cena visual faria mais sentido para o espectador.

**REGRAS IMPORTANTES:**
- O roteiro final, incluindo os marcadores, deve ter entre 2300 e 2400 caracteres. Siga este limite rigorosamente.
- Não numere os marcadores. Use sempre `[TROCAR_IMAGEM]`.
- Não inclua o número de caracteres na sua resposta final.
"""
        system_message = """Você é um teólogo e contador de histórias especialista em narrativas bíblicas. Sua missão é recontar as histórias da Bíblia de forma cativante, precisa e reverente, mantendo a essência teológica da passagem.

**ESTRUTURA:**
1.  **Abertura Atmosférica:** Comece com uma introdução que estabeleça o cenário e o contexto histórico/espiritual.
2.  **Desenvolvimento do Conflito/Milagre:** Apresente os personagens principais e o desafio ou evento divino central da história.
3.  **Clímax:** Descreva o momento mais impactante da narrativa.
4.  **Resolução e Lição:** Conclua a história com sua resolução e a lição de fé ou moral que ela transmite.

**TOM:**
A narrativa deve ser solene, inspiradora e acessível. Use uma linguagem que seja ao mesmo tempo poética e clara.

**IMPORTANTE:**
Sua resposta deve ser um texto único, contendo apenas a história com os marcadores inseridos."""

        headers = {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": Config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except requests.Timeout:
            raise TimeoutError(f"OpenRouter API excedeu {TIMEOUT_SECONDS}s")
        except requests.RequestException as e:
            raise ConnectionError(f"Falha na requisição OpenRouter: {e}")


    def generate_prompts(self, segmented_script: str) -> list:
        # 1. Try n8n Webhook
        if Config.N8N_PROMPTS_WEBHOOK_URL:
            try:
                payload = {"script_segmented": segmented_script}
                response = requests.post(Config.N8N_PROMPTS_WEBHOOK_URL, json=payload, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                data = response.json()
                if "image_prompts" in data:
                    return data["image_prompts"]
                if isinstance(data, list) and len(data) > 0 and "image_prompts" in data[0]:
                    return data[0]["image_prompts"]
            except Exception as e:
                print(f"Prompts Webhook failed: {e}. Trying fallback...")

        # 2. Fallback: Direct API
        if not Config.OPENROUTER_API_KEY:
             raise ValueError("OPENROUTER_API_KEY is required for direct prompt generation (no webhook configured).")

        prompt = f"""**TAREFA PRINCIPAL**
Sua missão é ser um Diretor de Arte e Cineasta. O roteiro abaixo já foi dividido em cenas numeradas. Sua tarefa é criar um prompt de imagem cinematográfico para **CADA CENA NUMERADA**.

**ESTILO VISUAL UNIFICADO (A "BÍBLIA" VISUAL)**
Este é o estilo que você deve aplicar a TODAS as imagens:
- **Estilo Principal:** Pintura Digital Épica, no estilo de arte conceitual do ArtStation (pense em Greg Rutkowski). Realismo com um toque de fantasia, cores vibrantes e detalhes épicos.
- **Iluminação:** Dramática (chiaroscuro), com raios de luz suaves e divinos.
- **Atmosfera:** Sagrada, com um senso de maravilha.
- **Paleta de Cores:** Dourados, tons terrosos, azuis celestiais, vermelhos profundos.

**DIREÇÃO NARRATIVA (MUITO IMPORTANTE)**
- **Consistência de Personagens:** Analise o roteiro para identificar os personagens principais (ex: Rute, Noemi, Boaz) e use uma descrição visual consistente para eles em todos os prompts.
- **Direção de Emoção:** Cada prompt deve capturar a emoção dominante da cena.
- **Direção de Câmera e Escala:** Varie os planos (Epic Wide Shot, Medium Shot, Dramatic Close-up) para criar um fluxo visual dinâmico.

**REGRAS DE SAÍDA (FORMATO JSON OBRIGATÓRIO)**
Sua resposta deve ser APENAS um array JSON dentro da chave `image_prompts`. Cada objeto no array representa uma cena e deve conter **APENAS** os seguintes campos:
- `prompt`: Um prompt de imagem curto, cinematográfico e escrito em **INGLÊS**.
- `image`: O nome sequencial da imagem (ex: "image_1").

**NÃO inclua o campo `sentence_indices` na sua resposta.**

Roteiro Segmentado:
{segmented_script}
"""
        system_message = "Você é um Diretor de Arte e Diretor de Fotografia para projetos de IA, especializado em iconografia religiosa e arte sacra. Você segue as instruções do usuário de forma rigorosa, prestando atenção especial ao formato de saída JSON solicitado."

        headers = {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": Config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']

            try:
                parsed = json.loads(content)
                return parsed.get("image_prompts", [])
            except json.JSONDecodeError:
                cleaned = content.replace("```json\n", "").replace("\n```", "")
                return json.loads(cleaned).get("image_prompts", [])
        except requests.Timeout:
            raise TimeoutError(f"OpenRouter API excedeu {TIMEOUT_SECONDS}s")
        except requests.RequestException as e:
            raise ConnectionError(f"Falha na requisição OpenRouter: {e}")


class TTSService:
    def generate_audio(self, text: str, output_path: Path):
        # 1. Try n8n Webhook
        if Config.N8N_TTS_WEBHOOK_URL:
            try:
                payload = {"text": text}
                # Expecting binary audio response
                response = requests.post(Config.N8N_TTS_WEBHOOK_URL, json=payload, stream=True, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return output_path
            except Exception as e:
                print(f"TTS Webhook failed: {e}. Trying fallback...")

        # 2. Fallback: OpenAI Direct
        if not Config.OPENAI_API_KEY:
             raise ValueError("OPENAI_API_KEY is required for TTS (no webhook configured).")

        headers = {
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": Config.TTS_MODEL,
            "voice": Config.TTS_VOICE,
            "input": text
        }

        try:
            response = requests.post("https://api.openai.com/v1/audio/speech", headers=headers, json=data, stream=True, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return output_path
        except requests.Timeout:
            raise TimeoutError(f"OpenAI TTS excedeu {TIMEOUT_SECONDS}s")
        except requests.RequestException as e:
            raise ConnectionError(f"Falha na requisição OpenAI TTS: {e}")


class STTService:
    def __init__(self):
        self.url = Config.SPEACHES_URL

    def transcribe(self, audio_path: Path) -> str:
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "audio/mpeg")}
            data = {
                "model": "Systran/faster-whisper-small",
                "response_format": "srt"
            }
            try:
                # Try Local/Configured URL
                response = requests.post(self.url, files=files, data=data, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                return response.text
            except Exception as e:
                print(f"STT Service at {self.url} failed: {e}. Trying OpenAI Fallback...")

                 # Fallback to OpenAI API
                if not Config.OPENAI_API_KEY:
                     raise ValueError("Speaches unreachable and OPENAI_API_KEY not set.")

                # We need to re-open the file because the pointer is at the end
                f.seek(0)

                headers = {
                    "Authorization": f"Bearer {Config.OPENAI_API_KEY}"
                }
                data_openai = {"model": "whisper-1", "response_format": "srt"}

                try:
                    response = requests.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers=headers,
                        files={"file": (audio_path.name, f, "audio/mpeg")},
                        data=data_openai,
                        timeout=TIMEOUT_SECONDS
                    )
                    response.raise_for_status()
                    return response.text
                except requests.Timeout:
                    raise TimeoutError(f"OpenAI Whisper excedeu {TIMEOUT_SECONDS}s")
                except requests.RequestException as e:
                    raise ConnectionError(f"Falha na requisição OpenAI Whisper: {e}")


class ImageGenService:
    def generate_image_openai(self, prompt: str, output_path: Path):
        # 1. Try n8n Webhook
        if Config.N8N_IMAGE_WEBHOOK_URL:
            try:
                payload = {"prompt": prompt}
                # Expecting binary image response
                response = requests.post(Config.N8N_IMAGE_WEBHOOK_URL, json=payload, stream=True, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return output_path
            except Exception as e:
                print(f"Image Webhook failed: {e}. Trying fallback...")

        # 2. Fallback: OpenAI DALL-E
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for Image Gen (no webhook).")

        headers = {
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": Config.IMAGE_MODEL_OPENAI,
            "prompt": f"{prompt}, 16:9 aspect ratio",
            "size": "1024x1024",
            "quality": "standard",
            "n": 1
        }

        try:
            response = requests.post("https://api.openai.com/v1/images/generations", headers=headers, json=data, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()

            image_url = response.json()['data'][0]['url']
            img_data = requests.get(image_url, timeout=TIMEOUT_SECONDS).content
            with open(output_path, 'wb') as handler:
                handler.write(img_data)
            return output_path
        except requests.Timeout:
            raise TimeoutError(f"OpenAI Image Gen excedeu {TIMEOUT_SECONDS}s")
        except requests.RequestException as e:
            raise ConnectionError(f"Falha na requisição OpenAI Image Gen: {e}")
