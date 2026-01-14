import json
import requests
from pathlib import Path
from openai import OpenAI
import google.generativeai as genai
from config import Config

class LLMService:
    def __init__(self):
        # Initialize OpenRouter client only if key is available
        if Config.OPENROUTER_API_KEY:
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=Config.OPENROUTER_API_KEY,
            )
        else:
            self.client = None

    def generate_script(self, story_topic: str, images_count: int) -> str:
        # Priority: n8n Webhook
        if Config.N8N_SCRIPT_WEBHOOK_URL:
            try:
                payload = {
                    "topic": story_topic,
                    "imageCount": images_count
                }
                response = requests.post(Config.N8N_SCRIPT_WEBHOOK_URL, json=payload)
                response.raise_for_status()
                data = response.json()

                # Check for "script" key as per n8n JSON response node
                if "script" in data:
                    return data["script"]
                # Sometimes n8n might return the full item list
                if isinstance(data, list) and len(data) > 0 and "script" in data[0]:
                    return data[0]["script"]

                # If structure is different, dump it for debugging or return raw text
                return response.text

            except Exception as e:
                # If webhook fails, try fallback if client is available, otherwise raise
                if self.client:
                    print(f"Webhook failed ({e}), falling back to direct API...")
                else:
                    raise Exception(f"Webhook failed and no OpenRouter Key provided: {e}")

        # Fallback: Direct API Call
        if not self.client:
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

        response = self.client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content

    def generate_prompts(self, segmented_script: str) -> list:
        # TODO: Implement n8n webhook for prompts if available

        if not self.client:
             raise ValueError("OPENROUTER_API_KEY is required for direct prompt generation (no webhook configured yet).")

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

        response = self.client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        try:
            parsed = json.loads(content)
            return parsed.get("image_prompts", [])
        except json.JSONDecodeError:
            # Fallback cleanup attempt
            cleaned = content.replace("```json\n", "").replace("\n```", "")
            return json.loads(cleaned).get("image_prompts", [])


class TTSService:
    def __init__(self):
        # Check if OpenAI Key exists, otherwise client is None
        if Config.OPENAI_API_KEY:
            self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        else:
            self.client = None

    def generate_audio(self, text: str, output_path: Path):
        # TODO: Add webhook support
        if not self.client:
             raise ValueError("OPENAI_API_KEY is required for TTS (no webhook configured).")

        response = self.client.audio.speech.create(
            model=Config.TTS_MODEL,
            voice=Config.TTS_VOICE,
            input=text
        )
        response.stream_to_file(output_path)
        return output_path


class STTService:
    def __init__(self):
        self.url = Config.SPEACHES_URL

    def transcribe(self, audio_path: Path) -> str:
        # Check if we should use local speaches or OpenAI whisper
        if "api.openai.com" in self.url:
             # Implementation for OpenAI API directly if needed, but keeping consistent with n8n flow which uses a custom endpoint usually
             pass

        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "audio/mpeg")}
            data = {
                "model": "Systran/faster-whisper-small",
                "response_format": "srt"
            }
            try:
                response = requests.post(self.url, files=files, data=data)
                response.raise_for_status()
                return response.text
            except requests.exceptions.ConnectionError:
                 # Fallback to OpenAI if local fails (optional, good for user experience)
                 if not Config.OPENAI_API_KEY:
                     raise ValueError("Speaches (local) unreachable and OPENAI_API_KEY not set.")

                 client = OpenAI(api_key=Config.OPENAI_API_KEY)
                 with open(audio_path, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="srt"
                    )
                    return transcription


class ImageGenService:
    def __init__(self):
        pass

    def generate_image_openai(self, prompt: str, output_path: Path):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for Image Gen.")

        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        response = client.images.generate(
            model=Config.IMAGE_MODEL_OPENAI,
            prompt=f"{prompt}, 16:9 aspect ratio",
            size="1024x1024", # DALL-E 2 standard
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        img_data = requests.get(image_url).content
        with open(output_path, 'wb') as handler:
            handler.write(img_data)
        return output_path

    def generate_image_google(self, prompt: str, output_path: Path):
        # Configure Google GenAI
        if not Config.GOOGLE_API_KEY:
             raise ValueError("GOOGLE_API_KEY is required for Google Image Gen.")

        genai.configure(api_key=Config.GOOGLE_API_KEY)

        # This is a placeholder for the actual Imagen model call via Gemini API
        # The specific model name and method might vary as Google updates the API
        # Assuming we use a model that supports image generation
        try:
             # Note: As of my knowledge cutoff, generic gemini-pro doesn't do image gen directly via this python lib in the same way.
             # Use requests if the library support is experimental.
             # However, let's try the library way if available or fallback to OpenAI.
             # For now, I'll implement a fallback to OpenAI if Google fails or is not configured.

             # If using Vertex AI or specific endpoint:
             pass
        except Exception as e:
            print(f"Google Image Gen failed: {e}. Falling back to OpenAI or skipping.")
            raise e
