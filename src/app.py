import streamlit as st
import os
from pathlib import Path
import json
import logging

from config import Config
from services import LLMService, TTSService, STTService, ImageGenService
from utils import (
    clean_script_initial,
    segment_script_with_markers,
    parse_srt,
    calculate_image_durations,
    setup_logger,
    validate_image_file,
    validate_audio_file
)
from media import get_audio_duration, create_video_from_images

# Page Config
st.set_page_config(page_title="AI Bible Story Generator", layout="wide")

# Session State Initialization
DEFAULT_STATE = {
    "step": 1,
    "project_slug": "",
    "script_raw": "",
    "prompts": [],
    "images_data": [],
    "production_done": False,
    "audio_generated": False,
    "srt_generated": False,
    "assets_generated": False
}

for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# Helper Functions
def render_progress_indicator():
    """Mostra progresso visual do projeto"""
    steps = [
        "📝 Roteiro",
        "✏️ Revisão",
        "🎙️ Áudio & Legendas",
        "🎬 Produção"
    ]

    cols = st.columns(4)
    for i, (col, step_name) in enumerate(zip(cols, steps), 1):
        with col:
            if i < st.session_state.step:
                st.success(f"✅ {step_name}")
            elif i == st.session_state.step:
                st.info(f"▶️ {step_name}")
            else:
                st.text(f"⭕ {step_name}")

    st.progress((st.session_state.step - 1) / 3)
    st.caption(f"Passo {st.session_state.step} de 4")
    st.markdown("---")

def render_project_status():
    """Mostra status do projeto atual na sidebar"""
    if not st.session_state.project_slug:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📂 Projeto Atual")
    st.sidebar.caption(f"**{st.session_state.project_slug}**")

    project_dir = Config.get_project_dir(st.session_state.project_slug)

    # Checklist de arquivos
    files_status = {
        "Roteiro": (project_dir / "roteiro_com_marcadores.txt").exists(),
        "Áudio": (project_dir / "narracao.mp3").exists(),
        "Legendas": (project_dir / "narracao.srt").exists(),
        "Prompts": (project_dir / "prompts.json").exists(),
        "Vídeo Final": (project_dir / "video_final.mp4").exists()
    }

    for item, exists in files_status.items():
        icon = "✅" if exists else "⭕"
        st.sidebar.text(f"{icon} {item}")

def init_services():
    return {
        "llm": LLMService(),
        "tts": TTSService(),
        "stt": STTService(),
        "img": ImageGenService()
    }

# Logger Setup
if st.session_state.project_slug:
    logger = setup_logger(st.session_state.project_slug)
else:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("bible_video_generic")

# Load Services
try:
    services = init_services()
    st.sidebar.success("Services Initialized")

    if Config.N8N_SCRIPT_WEBHOOK_URL:
        st.sidebar.info("Using n8n Webhook for Script")
    else:
        st.sidebar.warning("Using Local API Keys for Script")

    render_project_status()

except Exception as e:
    st.sidebar.error(f"Error initializing services: {e}")
    logger.error(f"Error initializing services: {e}")
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

                    # Update logger with new slug
                    logger = setup_logger(slug)
                    logger.info(f"Projeto criado: {slug}")

                    next_step()
                    st.rerun()
                except TimeoutError:
                    st.error("⏱️ **Timeout:** O servidor demorou muito para responder. Tente novamente.")
                except ConnectionError as e:
                    st.error(f"🌐 **Erro de Conexão:** Verifique sua internet. Detalhes: {e}")
                except ValueError as e:
                    st.error(f"⚠️ **Erro de Validação:** {e}")
                except Exception as e:
                    st.error(f"❌ **Erro Inesperado:** {e}")
                    st.info("💡 Tente recarregar a página ou contate o suporte.")
                    logger.exception("Erro ao gerar roteiro")

    # --- ABA: CARREGAR EXISTENTE ---
    with tab_load:
        output_dir = Path("output")
        if not output_dir.exists():
            st.warning("Nenhum projeto encontrado.")
        else:
            projects = [d.name for d in output_dir.iterdir() if d.is_dir()]
            if not projects:
                st.warning("Nenhum projeto encontrado.")
            else:
                selected_project = st.selectbox("Selecione o Projeto", projects)

                if st.button("Carregar Projeto"):
                    st.session_state.project_slug = selected_project
                    project_path = output_dir / selected_project

                    # 1. Carrega Roteiro
                    script_path = project_path / "roteiro_com_marcadores.txt"
                    if script_path.exists():
                        with open(script_path, "r") as f:
                            st.session_state.script_raw = f.read()

                    # VERIFICAÇÃO INTELIGENTE DE STATUS
                    has_video = (project_path / "video_final.mp4").exists()
                    has_prompts = (project_path / "prompts.json").exists()
                    has_audio = (project_path / "narracao.mp3").exists()

                    if has_video:
                        st.session_state.step = 4
                        st.session_state.production_done = True

                    elif has_prompts:
                        st.session_state.step = 4
                        # Carrega os prompts para a memória
                        with open(project_path / "prompts.json", "r", encoding="utf-8") as f:
                            st.session_state.prompts = json.load(f)

                    elif has_audio:
                        st.session_state.step = 3

                    else:
                        st.session_state.step = 2

                    logger = setup_logger(selected_project)
                    logger.info(f"Projeto carregado: {selected_project}")
                    st.success(f"Projeto '{selected_project}' carregado! Indo para o passo {st.session_state.step}...")
                    st.rerun()

# ==============================================================================
# STEP 2: EDIT SCRIPT
# ==============================================================================
elif st.session_state.step == 2:
    st.title("Passo 2: Review & Edit Script")
    render_progress_indicator()

    st.info("Edit the script below. ensure you keep the [TROCAR_IMAGEM] markers!")

    new_script = st.text_area("Script", st.session_state.script_raw, height=600)
    st.session_state.script_raw = new_script

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("✅ Confirmar Roteiro e Avançar"):
            try:
                # Salva o roteiro editado
                project_dir = Config.get_project_dir(st.session_state.project_slug)
                script_clean, script_markers = clean_script_initial(st.session_state.script_raw)

                with open(project_dir / "roteiro_com_marcadores.txt", "w") as f:
                    f.write(script_markers)
                with open(project_dir / "roteiro_limpo.txt", "w") as f:
                    f.write(script_clean)

                next_step()
                st.rerun()
            except Exception as e:
                logger.error(f"Erro ao salvar roteiro: {e}")
                st.error(f"Erro ao salvar: {e}")

# ==============================================================================
# STEP 3: AUDIO, LEGENDAS E PROMPTS
# ==============================================================================
elif st.session_state.step == 3:
    st.title("Passo 3: Áudio e Legendas")
    render_progress_indicator()

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
        with open(script_clean_path, "r") as f:
            script_clean = f.read()

    # --- SEÇÃO 1: ÁUDIO (NARRAÇÃO) ---
    st.header("1. Narração (Áudio)")

    audio_path = project_dir / "narracao.mp3"

    tab_audio_ia, tab_audio_manual = st.tabs(["🤖 Gerar com IA", "📤 Upload Manual (Narrador Humano)"])

    with tab_audio_ia:
        st.write("Gere a narração automaticamente usando o serviço configurado.")
        if st.button("Gerar Áudio (IA)"):
            with st.spinner("Gerando narração..."):
                try:
                    services["tts"].generate_audio(script_clean, audio_path)
                    st.success("Áudio gerado com sucesso!")
                    st.rerun()
                except TimeoutError:
                    st.error("⏱️ **Timeout:** O servidor de TTS demorou muito.")
                except Exception as e:
                    logger.error(f"Erro TTS: {e}")
                    st.error(f"Erro ao gerar áudio: {e}")

    with tab_audio_manual:
        st.write("Baixe o roteiro para enviar ao narrador e depois suba o MP3 pronto.")

        st.download_button(
            label="📄 Baixar Roteiro (TXT) para Narrador",
            data=script_clean,
            file_name=f"roteiro_{st.session_state.project_slug}.txt",
            mime="text/plain"
        )

        uploaded_audio = st.file_uploader("Upload do Arquivo MP3", type=["mp3"])
        if uploaded_audio is not None:
            with open(audio_path, "wb") as f:
                f.write(uploaded_audio.getbuffer())

            # Validate
            if validate_audio_file(audio_path):
                st.success("✅ MP3 enviado e validado!")
            else:
                os.remove(audio_path)
                st.error("❌ Arquivo de áudio corrompido. Tente novamente.")

    if audio_path.exists():
        st.audio(str(audio_path))

    st.markdown("---")

    # --- SEÇÃO 2: LEGENDAS (SRT) ---
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
                    except TimeoutError:
                        st.error("⏱️ **Timeout:** O servidor de STT demorou muito.")
                    except Exception as e:
                        logger.error(f"Erro STT: {e}")
                        st.error(f"Erro na transcrição: {e}")

        with tab_srt_manual:
            st.write("Faça o upload dos arquivos de legenda.")

            col_srt, col_json = st.columns(2)

            with col_srt:
                uploaded_srt = st.file_uploader("1. Arquivo .SRT (Obrigatório para legendas)", type=["srt"])
                if uploaded_srt is not None:
                    with open(srt_path, "wb") as f:
                        f.write(uploaded_srt.getbuffer())
                    st.success("SRT salvo!")

            with col_json:
                uploaded_json = st.file_uploader("2. JSON Word-Level (Opcional - Sincronia Pro)", type=["json"])
                if uploaded_json is not None:
                    json_path = project_dir / "transcription.json"
                    with open(json_path, "wb") as f:
                        f.write(uploaded_json.getbuffer())
                    st.success("JSON Pro salvo!")

            if uploaded_srt is not None or uploaded_json is not None:
                st.rerun()

        if srt_path.exists():
            with st.expander("Ver arquivo SRT"):
                with open(srt_path, "r") as f:
                    st.text(f.read())

    # --- SEÇÃO 3: PROMPTS ---
    st.markdown("---")

    if audio_path.exists() and (project_dir / "narracao.srt").exists():

        st.header("3. Geração de Prompts")

        prompts_path = project_dir / "prompts.json"

        if prompts_path.exists():
            st.info("✅ Prompts já encontrados neste projeto.")
            col_skip, col_regen = st.columns([1, 1])

            with col_skip:
                if st.button("Pular Geração e Ir para Produção ➡", type="primary"):
                    with open(prompts_path, "r", encoding="utf-8") as f:
                        st.session_state.prompts = json.load(f)
                    next_step()
                    st.rerun()

            with col_regen:
                if st.button("Gerar Novos Prompts (Sobrescrever)"):
                    generate_prompts_logic = True
                else:
                    generate_prompts_logic = False
        else:
            if st.button("Gerar Prompts de Imagem ➡"):
                generate_prompts_logic = True
            else:
                generate_prompts_logic = False

        if generate_prompts_logic:
            with st.spinner("Criando descrições visuais para as cenas..."):
                try:
                    with open(script_markers_path, "r") as f:
                        script_markers = f.read()

                    segments = segment_script_with_markers(script_markers)
                    segmented_text = "\n\n".join([f"{i+1}. {s}" for i, s in enumerate(segments)])

                    prompts_list = services["llm"].generate_prompts(segmented_text)

                    st.session_state.prompts = prompts_list

                    with open(prompts_path, "w", encoding="utf-8") as f:
                        json.dump(prompts_list, f, indent=4, ensure_ascii=False)

                    next_step()
                    st.rerun()
                except TimeoutError:
                     st.error("⏱️ **Timeout:** Geração de prompts demorou muito.")
                except Exception as e:
                    logger.error(f"Erro Prompts: {e}")
                    st.error(f"Erro ao gerar prompts: {e}")
    else:
        st.warning("⚠️ Complete as etapas de Áudio e Legenda acima para avançar.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("⬅ Voltar para Roteiro"):
        prev_step()
        st.rerun()
# ==============================================================================
# STEP 4: IMAGES & VIDEO PRODUCTION
# ==============================================================================
elif st.session_state.step == 4:
    st.title("Passo 4: Produção & Renderização")
    render_progress_indicator()

    # Botão de Voltar com Confirmação
    col_back, col_space = st.columns([1, 3])
    with col_back:
        if st.button("⬅ Voltar", type="secondary"):
            # Verifica se há imagens geradas
            project_dir = Config.get_project_dir(st.session_state.project_slug) # Ensure project_dir is defined
            has_images = st.session_state.images_data or (project_dir / "prompts.json").exists()

            if has_images:
                st.warning("⚠️ Imagens e prompts serão mantidos. Deseja voltar?")
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    if st.button("✅ Sim, voltar"):
                        prev_step()
                        st.rerun()
                with col_cancel:
                    if st.button("❌ Cancelar"):
                        st.rerun()
            else:
                prev_step()
                st.rerun()

    project_dir = Config.get_project_dir(st.session_state.project_slug)

    # --- RECUPERAÇÃO DE ESTADO ---
    if not st.session_state.prompts:
        prompts_path = project_dir / "prompts.json"
        if prompts_path.exists():
            with open(prompts_path, "r", encoding="utf-8") as f:
                st.session_state.prompts = json.load(f)
        else:
            st.warning("Nenhum prompt encontrado. Volte ao passo anterior.")
            st.stop()

    if "production_done" not in st.session_state:
        st.session_state.production_done = False

    # --- CONFIGURAÇÃO DE SAÍDA ---
    st.markdown("### ⚙️ Configuração do Vídeo")
    video_format = st.selectbox(
        "Formato e Resolução",
        options=[
            "Vertical (9:16) - Full HD (1080x1920)",
            "Vertical (9:16) - 4K (2160x3840)",
            "Horizontal (16:9) - Full HD (1920x1080)",
            "Horizontal (16:9) - 4K (3840x2160)"
        ],
        index=0
    )

    if "4K" in video_format:
        st.info("ℹ️ Modo 4K: Recomendado fazer Upscale das imagens externamente e usar a aba 'Estúdio Manual'.")

    st.markdown("---")

    # --- FUNÇÃO WRAPPER DE RENDERIZAÇÃO ---
    def run_render_pipeline(progress_bar_obj, status_text_obj):
        """Executa a lógica de Sincronia e FFmpeg passando o formato escolhido."""
        try:
            status_text_obj.text("Sincronizando Roteiro e Áudio...")

            with open(project_dir / "roteiro_com_marcadores.txt", "r") as f:
                script_markers = f.read()
            segments = segment_script_with_markers(script_markers)

            audio_path = project_dir / "narracao.mp3"
            audio_duration = get_audio_duration(audio_path)

            json_path = project_dir / "transcription.json"
            if json_path.exists():
                from utils import parse_json_transcription, calculate_durations_from_words
                with open(json_path, "r") as f:
                    word_data = parse_json_transcription(f.read())
                images_data = calculate_durations_from_words(segments, word_data, audio_duration)
            else:
                with open(project_dir / "narracao.srt", "r") as f:
                    srt_content = f.read()
                subtitles = parse_srt(srt_content)
                images_data = calculate_image_durations(segments, subtitles, audio_duration)

            st.session_state.images_data = images_data

            if progress_bar_obj: progress_bar_obj.progress(0.9)

            status_text_obj.text(f"Renderizando Vídeo Final ({video_format})...")

            create_video_from_images(images_data, audio_path, project_dir, video_format)

            if progress_bar_obj: progress_bar_obj.progress(1.0)
            status_text_obj.text("Produção Completa!")

            st.session_state.production_done = True
            st.balloons()
            st.rerun()

        except Exception as e:
            logger.error(f"Erro Crítico Render: {e}")
            st.error(f"Erro Crítico na Renderização: {e}")
            print(f"Erro Render: {e}")

    # TELA DE EDIÇÃO/PRODUÇÃO
    if not st.session_state.production_done:

        tab_auto, tab_manual = st.tabs(["🚀 Produção Automática", "🎨 Estúdio Manual (Upscale/Troca)"])

        # --- ABA 1: AUTOMÁTICA ---
        with tab_auto:
            st.info("Gera imagens via API e renderiza automaticamente.")
            if st.button("Iniciar Produção Automática"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                try:
                    total_images = len(st.session_state.prompts)
                    for i, p_data in enumerate(st.session_state.prompts):
                        status_text.text(f"Gerando Imagem {i+1}/{total_images}...")
                        image_name = p_data['image']
                        image_path = project_dir / f"{image_name}.jpg"

                        if not image_path.exists():
                             services["img"].generate_image_openai(p_data['prompt'], image_path)

                        progress_bar.progress((i + 1) / (total_images + 2))

                    run_render_pipeline(progress_bar, status_text)
                except Exception as e:
                    logger.error(f"Erro Prod Auto: {e}")
                    st.error(f"Falha na produção: {e}")

        # --- ABA 2: MANUAL (COM SUPORTE A ARQUIVOS RAW) ---
        with tab_manual:
            st.markdown("### Gerenciamento de Imagens")
            st.caption("Dica: Use esta aba para subir imagens 4K ou feitas no Midjourney.")

            total_images = len(st.session_state.prompts)
            imgs_uploaded_count = 0

            for i, p_data in enumerate(st.session_state.prompts):
                image_name = p_data['image']

                found_file = None
                for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                    f_path = project_dir / f"{image_name}{ext}"
                    if f_path.exists():
                        found_file = f_path
                        break

                with st.expander(f"🖼️ Cena {i+1}: {image_name}", expanded=(found_file is None)):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.caption("Prompt:")
                        st.code(p_data['prompt'], language="text")
                    with c2:
                        if found_file:
                            st.success("✅ Pronta")
                            st.image(str(found_file), use_container_width=True)
                            imgs_uploaded_count += 1

                            if st.button("🗑️ Trocar", key=f"del_{i}"):
                                try:
                                    os.remove(found_file)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao remover: {e}")
                        else:
                            up = st.file_uploader(f"Upload {image_name}", type=["jpg", "png", "jpeg", "webp"], key=f"u_{i}")
                            if up:
                                try:
                                    original_ext = Path(up.name).suffix.lower()
                                    if not original_ext: original_ext = ".jpg"

                                    save_path = project_dir / f"{image_name}{original_ext}"

                                    with open(save_path, "wb") as f:
                                        f.write(up.getbuffer())

                                    # Validate uploaded image
                                    if validate_image_file(save_path):
                                        st.rerun()
                                    else:
                                        os.remove(save_path)
                                        st.error("Imagem inválida.")
                                except Exception as e:
                                    st.error(f"Erro ao salvar: {e}")

            st.markdown("---")

            if imgs_uploaded_count == total_images:
                st.success(f"Todas as {total_images} imagens estão prontas.")

                if st.button("🎬 Renderizar Vídeo Final", type="primary"):
                    st_text = st.empty()
                    run_render_pipeline(None, st_text)
            else:
                st.warning(f"Faltam {total_images - imgs_uploaded_count} imagens para renderizar.")

    # TELA FINAL (Pós-Produção)
    else:
        st.success("Vídeo Gerado com Sucesso! 🎉")
        video_path = project_dir / "video_final.mp4"

        if video_path.exists():
            st.video(str(video_path))
            with open(video_path, "rb") as file:
                st.download_button("⬇️ Baixar MP4", file, file_name=f"{st.session_state.project_slug}.mp4")

        col_new, col_edit = st.columns(2)
        with col_new:
            if st.button("Iniciar Novo Projeto"):
                st.session_state.step = 1
                st.session_state.production_done = False
                st.session_state.prompts = []
                st.rerun()

        with col_edit:
            if st.button("🛠️ Ajustar e Renderizar Novamente"):
                st.session_state.production_done = False
                st.rerun()
