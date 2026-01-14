import streamlit as st
import os
from pathlib import Path
import json

from config import Config
from services import LLMService, TTSService, STTService, ImageGenService
from utils import (
    clean_script_initial,
    segment_script_with_markers,
    parse_srt,
    calculate_image_durations
)
from media import get_audio_duration, create_video_from_images

# Page Config
st.set_page_config(page_title="AI Bible Story Generator", layout="wide")

# Session State Initialization
if "step" not in st.session_state:
    st.session_state.step = 1
if "project_slug" not in st.session_state:
    st.session_state.project_slug = ""
if "script_raw" not in st.session_state:
    st.session_state.script_raw = ""
if "prompts" not in st.session_state:
    st.session_state.prompts = []
if "images_data" not in st.session_state:
    st.session_state.images_data = []

def init_services():
    return {
        "llm": LLMService(),
        "tts": TTSService(),
        "stt": STTService(),
        "img": ImageGenService()
    }

# Load Services
try:
    services = init_services()
    st.sidebar.success("Services Initialized")

    if Config.N8N_SCRIPT_WEBHOOK_URL:
        st.sidebar.info("Using n8n Webhook for Script")
    else:
        st.sidebar.warning("Using Local API Keys for Script")

except Exception as e:
    st.sidebar.error(f"Error initializing services: {e}")
    st.stop()

# Helper to advance steps
def next_step():
    st.session_state.step += 1

def prev_step():
    st.session_state.step -= 1

# ==============================================================================
# STEP 1: SETUP OU CARREGAR PROJETO
# ==============================================================================
if st.session_state.step == 1:
    st.title("Passo 1: Início")

    # Verifica configuração
    is_valid, msg = Config.validate()
    if not is_valid:
        st.error(msg)
        st.stop()

    # Abas para Novo Projeto ou Carregar Existente
    tab_new, tab_load = st.tabs(["🆕 Novo Projeto", "📂 Carregar Existente"])

    # --- ABA: NOVO PROJETO ---
    with tab_new:
        topic = st.text_input("Tema da História Bíblica", "José no Egito")
        num_images = st.number_input("Número de Imagens", min_value=3, max_value=50, value=10)

        if st.button("Gerar Roteiro"):
            with st.spinner("Gerando roteiro com LLM..."):
                try:
                    # Gera roteiro
                    script = services["llm"].generate_script(topic, num_images)
                    st.session_state.script_raw = script

                    # Gera Slug e Pasta
                    slug = topic.lower().replace(" ", "-")
                    # Remove acentos do slug (opcional, mas recomendado)
                    import unicodedata
                    slug = "".join(c for c in unicodedata.normalize('NFD', slug) if unicodedata.category(c) != 'Mn')
                    st.session_state.project_slug = slug

                    Config.get_project_dir(slug)

                    next_step()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gerar roteiro: {e}")

    # --- ABA: CARREGAR EXISTENTE ---
    with tab_load:
        # Lista pastas dentro de ./output
        output_dir = Config.BASE_DIR
        if output_dir.exists():
            # Pega apenas diretórios
            projects = [f.name for f in output_dir.iterdir() if f.is_dir()]

            if projects:
                selected_project = st.selectbox("Selecione um projeto salvo:", projects)

                if st.button("Carregar Projeto"):
                    st.session_state.project_slug = selected_project
                    project_path = output_dir / selected_project

                    # Tenta recuperar o estado baseando-se nos arquivos que existem

                    # 1. Carrega Roteiro
                    script_path = project_path / "roteiro_com_marcadores.txt"
                    if script_path.exists():
                        with open(script_path, "r") as f:
                            st.session_state.script_raw = f.read()

                    # Lógica inteligente para saber para qual passo ir
                    has_video = (project_path / "video_final.mp4").exists()
                    has_audio = (project_path / "narracao.mp3").exists()
                    has_prompts = False # Difícil validar sem salvar o json dos prompts, mas assumimos Passo 3 ou 4

                    if has_video:
                        st.session_state.step = 5 # Vai para tela final (ajustaremos os passos depois)
                        st.session_state.production_done = True
                    elif has_audio:
                        st.session_state.step = 3 # Vai para tela de Áudio/Prompts

                        # Tenta carregar os prompts se existirem
                        prompts_file = project_path / "prompts.json"
                        if prompts_file.exists():
                            with open(prompts_file, "r", encoding="utf-8") as f:
                                st.session_state.prompts = json.load(f)
                    else:
                        st.session_state.step = 2 # Vai para edição de roteiro

                    st.success(f"Projeto '{selected_project}' carregado! Indo para o passo {st.session_state.step}...")
                    st.rerun()
            else:
                st.info("Nenhum projeto encontrado na pasta output.")
        else:
            st.warning("Pasta de output ainda não existe.")

# ==============================================================================
# STEP 2: EDIT SCRIPT
# ==============================================================================
elif st.session_state.step == 2:
    st.title("Step 2: Review & Edit Script")

    st.info("Edit the script below. ensure you keep the [TROCAR_IMAGEM] markers!")

    new_script = st.text_area("Script", st.session_state.script_raw, height=600)
    st.session_state.script_raw = new_script

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Confirm Script & Generate Audio/Prompts"):
            next_step()
            st.rerun()
# ==============================================================================
# STEP 3: AUDIO, LEGENDAS E PROMPTS
# ==============================================================================
elif st.session_state.step == 3:
    st.title("Passo 3: Áudio e Legendas")

    project_dir = Config.get_project_dir(st.session_state.project_slug)

    # Prepara o roteiro limpo se ainda não existir
    script_clean_path = project_dir / "roteiro_limpo.txt"
    script_markers_path = project_dir / "roteiro_com_marcadores.txt"

    if not script_markers_path.exists():
        script_clean, script_markers = clean_script_initial(st.session_state.script_raw)
        with open(script_markers_path, "w") as f:
            f.write(script_markers)
        with open(script_clean_path, "w") as f:
            f.write(script_clean)
    else:
        # Lê o limpo para o botão de download
        with open(script_clean_path, "r") as f:
            script_clean = f.read()

    # --- SEÇÃO 1: ÁUDIO (NARRAÇÃO) ---
    st.header("1. Narração (Áudio)")

    audio_path = project_dir / "narracao.mp3"
    audio_exists = audio_path.exists()

    tab_audio_ia, tab_audio_manual = st.tabs(["🤖 Gerar com IA", "📤 Upload Manual (Narrador Humano)"])

    with tab_audio_ia:
        st.write("Gere a narração automaticamente usando o serviço configurado.")
        if st.button("Gerar Áudio (IA)"):
            with st.spinner("Gerando narração..."):
                try:
                    services["tts"].generate_audio(script_clean, audio_path)
                    st.success("Áudio gerado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gerar áudio: {e}")

    with tab_audio_manual:
        st.write("Baixe o roteiro para enviar ao narrador e depois suba o MP3 pronto.")

        # Botão de Download do Roteiro
        st.download_button(
            label="📄 Baixar Roteiro (TXT) para Narrador",
            data=script_clean,
            file_name=f"roteiro_{st.session_state.project_slug}.txt",
            mime="text/plain"
        )

        # Upload do MP3
        uploaded_audio = st.file_uploader("Upload do Arquivo MP3", type=["mp3"])
        if uploaded_audio is not None:
            with open(audio_path, "wb") as f:
                f.write(uploaded_audio.getbuffer())
            st.success("MP3 enviado com sucesso!")
            st.rerun()

    # Player de confirmação
    if audio_path.exists():
        st.audio(str(audio_path))

    st.markdown("---")

    # --- SEÇÃO 2: LEGENDAS (SRT) ---
    # Só libera se tiver áudio
    if audio_path.exists():
        st.header("2. Legendas e Sincronia")

        srt_path = project_dir / "narracao.srt"

        tab_srt_ia, tab_srt_manual = st.tabs(["🤖 Gerar Automático (Transcrever)", "📤 Upload SRT"])

        with tab_srt_ia:
            st.write("Criar legendas analisando o áudio (Speech-to-Text).")
            if st.button("Gerar Legendas e Sincronia"):
                with st.spinner("Transcrevendo áudio..."):
                    try:
                        srt_content = services["stt"].transcribe(audio_path)
                        with open(srt_path, "w") as f:
                            f.write(srt_content)
                        st.success("Legendas geradas!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro na transcrição: {e}")

        with tab_srt_manual:
            st.write("Já tem o arquivo SRT? Faça o upload aqui.")
            uploaded_srt = st.file_uploader("Upload do Arquivo .SRT", type=["srt"])
            if uploaded_srt is not None:
                # Converter bytes para string para salvar ou salvar direto bytes
                with open(srt_path, "wb") as f:
                    f.write(uploaded_srt.getbuffer())
                st.success("SRT enviado com sucesso!")
                st.rerun()

        if srt_path.exists():
            with st.expander("Ver arquivo SRT"):
                with open(srt_path, "r") as f:
                    st.text(f.read())

    # --- SEÇÃO 3: PROMPTS ---
    st.markdown("---")

    # Só avança para prompts se tiver áudio e legenda
    if audio_path.exists() and (project_dir / "narracao.srt").exists():
        col_next_1, col_next_2 = st.columns([3, 1])
        with col_next_2:
            # Aqui geramos os prompts apenas ao avançar, ou podemos criar um botão específico
            if st.button("Gerar Prompts de Imagem ➡"):
                with st.spinner("Criando descrições visuais para as cenas..."):
                    try:
                        # Recupera o roteiro com marcadores
                        with open(script_markers_path, "r") as f:
                            script_markers = f.read()

                        segments = segment_script_with_markers(script_markers)
                        segmented_text = "\n\n".join([f"{i+1}. {s}" for i, s in enumerate(segments)])

                        prompts_list = services["llm"].generate_prompts(segmented_text)
                        st.session_state.prompts = prompts_list

                        # Salva no ARQUIVO (para não perder se fechar)
                        prompts_path = project_dir / "prompts.json"
                        with open(prompts_path, "w", encoding="utf-8") as f:
                            json.dump(prompts_list, f, indent=4, ensure_ascii=False)

                        next_step() # Vai para o passo 4 (Edição de Prompts e Produção)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao gerar prompts: {e}")
    else:
        st.warning("⚠️ Complete as etapas de Áudio e Legenda acima para avançar.")

    # Botão Voltar
    if st.button("⬅ Voltar para Roteiro"):
        prev_step()
        st.rerun()
# ==============================================================================
# STEP 4: IMAGES & VIDEO PRODUCTION
# ==============================================================================
elif st.session_state.step == 4:
    st.title("Step 4: Production")

    project_dir = Config.get_project_dir(st.session_state.project_slug)

    if "production_done" not in st.session_state:
        st.session_state.production_done = False

    if not st.session_state.production_done:
        start_btn = st.button("Start Production")
        if start_btn:
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                # 1. Generate Images
                total_images = len(st.session_state.prompts)

                for i, p_data in enumerate(st.session_state.prompts):
                    status_text.text(f"Generating Image {i+1}/{total_images}...")
                    image_name = p_data['image'] # e.g. "image_1"
                    image_path = project_dir / f"{image_name}.jpg"

                    if not image_path.exists():
                         services["img"].generate_image_openai(p_data['prompt'], image_path)

                    progress_bar.progress((i + 1) / (total_images + 2))

                # 2. Sync Logic (Calculate Durations)
                status_text.text("Synchronizing Script with Audio...")

                # Read SRT
                with open(project_dir / "narracao.srt", "r") as f:
                    srt_content = f.read()
                subtitles = parse_srt(srt_content)

                # Get script segments again
                with open(project_dir / "roteiro_com_marcadores.txt", "r") as f:
                    script_markers = f.read()
                segments = segment_script_with_markers(script_markers)

                # Get audio duration
                audio_path = project_dir / "narracao.mp3"
                audio_duration = get_audio_duration(audio_path)

                # Calculate
                images_data = calculate_image_durations(segments, subtitles, audio_duration)
                st.session_state.images_data = images_data

                progress_bar.progress((total_images + 1) / (total_images + 2))

                # 3. Render Video
                status_text.text("Rendering Final Video (FFmpeg)...")
                final_video_path = create_video_from_images(images_data, audio_path, project_dir)

                progress_bar.progress(1.0)
                status_text.text("Production Complete!")
                st.session_state.production_done = True
                st.balloons()
                st.rerun()

            except Exception as e:
                st.error(f"Production failed: {e}")

    else:
        st.success("Video Generated Successfully!")
        project_dir = Config.get_project_dir(st.session_state.project_slug)
        video_path = project_dir / "video_final.mp4"

        if video_path.exists():
            st.video(str(video_path))

        if st.button("Start New Project"):
            st.session_state.step = 1
            st.session_state.assets_generated = False
            st.session_state.production_done = False
            st.rerun()
