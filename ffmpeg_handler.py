# ffmpeg_handler.py
# Módulo para lidar com todas as interações com FFmpeg e ffprobe.
# VERSÃO FINAL - Com lógica para efeitos incrementais e preview funcional para ambos.

import subprocess
import re
import os
import tempfile
import logging
import traceback
import uuid
import json
import signal
from typing import List, Dict, Optional, Any
from fractions import Fraction # CORREÇÃO: Importado para substituir eval() de forma segura

# CORREÇÃO: Importações adicionais do arquivo de configuração
from config import ASS_HEADER_TEMPLATE, ASS_STYLES, QUALIDADE_MAP, LAYERS_PER_TRACK

# É necessário importar srt e timedelta para a correção do preview
import srt
from datetime import timedelta


class FFmpegHandler:
    # Caminho configurável para FFmpeg - pode ser definido via variável de ambiente
    FFMPEG_BIN_PATH = os.environ.get('FFMPEG_PATH', r'C:\ffmpeg\bin')

    def __init__(self, progress_queue, effect_classes: dict):
        self.progress_queue = progress_queue
        self.process = None
        self.effect_classes = effect_classes

    def _get_executable(self, name: str) -> str:
        """Retorna o caminho completo para ffmpeg.exe ou ffprobe.exe."""
        custom_path = os.path.join(self.FFMPEG_BIN_PATH, f'{name}.exe')
        if os.path.exists(custom_path):
            return custom_path

        import shutil
        system_path = shutil.which(name)
        if system_path:
            return system_path

        return custom_path

    def get_video_duration(self, file_path: str) -> Optional[float]:
        """Obtém a duração de um arquivo de vídeo usando ffprobe."""
        if not os.path.exists(file_path):
            self.progress_queue.put(('error', "Arquivo de vídeo não encontrado."))
            return None

        try:
            command = [
                self._get_executable('ffprobe'), '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', file_path
            ]
            # CORREÇÃO: Adicionado timeout para evitar travamentos
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            return float(result.stdout.strip())

        except FileNotFoundError:
            error_msg = f"FFmpeg não encontrado. Verifique se está instalado e no PATH ou configure FFMPEG_PATH."
            logging.error(error_msg)
            self.progress_queue.put(('error', error_msg))
            return None
        except subprocess.TimeoutExpired:
            error_msg = "O FFmpeg demorou demais para responder (timeout) ao obter a duração do vídeo."
            logging.error(error_msg)
            self.progress_queue.put(('error', error_msg))
            return None
        except (subprocess.CalledProcessError, ValueError) as e:
            error_msg = f"Falha ao ler duração do vídeo: {e}"
            logging.error(error_msg)
            self.progress_queue.put(('error', error_msg))
            return None

    def get_video_info(self, file_path: str) -> Optional[Dict]:
        """Obtém informações detalhadas do vídeo"""
        if not os.path.exists(file_path):
            return None

        try:
            command = [
                self._get_executable('ffprobe'), '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', file_path
            ]
            # CORREÇÃO: Adicionado timeout para evitar travamentos
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)

            info = json.loads(result.stdout)

            video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
            if video_stream:
                # CORREÇÃO DE SEGURANÇA: Substituído eval() por Fraction para calcular o FPS
                frame_rate_str = video_stream.get('r_frame_rate', '30/1')
                fps = float(Fraction(frame_rate_str))

                return {
                    'duration': float(info['format'].get('duration', 0)),
                    'width': int(video_stream.get('width', 1920)),
                    'height': int(video_stream.get('height', 1080)),
                    'fps': fps
                }
        except subprocess.TimeoutExpired:
            logging.warning("O FFmpeg demorou demais para responder (timeout) ao obter informações do vídeo.")
        except Exception as e:
            logging.warning(f"Falha ao obter informações do vídeo: {e}")

        return None

    def cancel_process(self):
        """Solicita o cancelamento do processo FFmpeg em andamento e seus filhos."""
        if self.process and self.process.poll() is None:
            logging.info("Cancelamento solicitado pelo usuário. Encerrando grupo de processos FFmpeg.")
            self.progress_queue.put(('status', 'Cancelando...'))
            try:
                # CORREÇÃO: Implementado cancelamento "à prova de zumbis"
                if os.name == 'nt':
                    # No Windows, envia um sinal de interrupção para o grupo de processos
                    self.process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    # Em sistemas Unix-like, encerra o grupo de processos inteiro
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

                self.process.terminate() # Garante o término se o sinal falhar
                self.process.wait(timeout=5) # Espera um pouco para o processo fechar
            except (ProcessLookupError, OSError, subprocess.TimeoutExpired) as e:
                logging.warning(f"Não foi possível encerrar o processo FFmpeg de forma limpa: {e}")
            finally:
                self.process = None


    def process_video(self, video_path: str, tracks: List[Dict], quality_key: str, limit_duration: Optional[str], encoder_type: str = "CPU"):
        """Função principal que orquestra a geração do ASS e a renderização do vídeo."""
        ass_file_path = ""
        temp_files = []

        try:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {video_path}")

            video_info = self.get_video_info(video_path)
            if not video_info:
                raise RuntimeError("Não foi possível obter as informações do vídeo de entrada.")

            total_duration = video_info['duration']

            all_dialogue_lines, required_styles = self._generate_all_ass_lines(tracks)

            if not all_dialogue_lines:
                raise ValueError("Nenhum efeito foi gerado. Verifique os arquivos SRT e as configurações.")

            # CORREÇÃO: Validar se todos os estilos requeridos pelos efeitos existem no config.py
            for style_name in required_styles:
                if style_name not in ASS_STYLES:
                    raise ValueError(f"Estilo '{style_name}' é necessário mas não foi encontrado no arquivo de configuração.")

            self.progress_queue.put(('status', 'Gerando arquivo .ass...'))

            style_block = "\n".join(
                ASS_STYLES[style_name] for style_name in sorted(list(required_styles))
            )

            # CORREÇÃO: Adotada resolução dinâmica para o cabeçalho do ASS
            ass_header = ASS_HEADER_TEMPLATE.format(width=video_info['width'], height=video_info['height'])

            ass_content = (
                f"{ass_header}{style_block}\n\n[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                + "\n".join(all_dialogue_lines)
            )

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ass', encoding='utf-8') as temp_ass_file:
                temp_ass_file.write(ass_content)
                ass_file_path = temp_ass_file.name
                temp_files.append(ass_file_path)

            command = self._build_ffmpeg_command(video_path, ass_file_path, quality_key, limit_duration, encoder_type)

            self.progress_queue.put(('status', 'Renderizando com FFmpeg...'))
            logging.info(f"Executando comando FFmpeg: {' '.join(command)}")

            # CORREÇÃO: Adicionadas flags para criação de grupo de processos para cancelamento robusto
            popen_kwargs = {
                'stderr': subprocess.PIPE,
                'stdout': subprocess.DEVNULL,
                'text': True,
                'encoding': 'utf-8',
                'errors': 'ignore'
            }
            if os.name == 'nt':
                popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs['start_new_session'] = True

            self.process = subprocess.Popen(command, **popen_kwargs)

            duration_for_progress = float(limit_duration) if limit_duration and limit_duration.isdigit() else total_duration
            self._monitor_progress(duration_for_progress)

            return_code = self.process.wait()
            output_file = command[-1]

            if return_code == 0:
                self.progress_queue.put(('finished', output_file))
            elif self.progress_queue.queue and self.progress_queue.queue[-1][1] == 'Cancelando...':
                self.progress_queue.put(('cancelled', ''))
            else:
                raise RuntimeError(f"Erro no FFmpeg (código: {return_code}). Verifique o console para detalhes.")

        except Exception as e:
            logging.error(traceback.format_exc())
            self.progress_queue.put(('error', str(e)))
        finally:
            self._cleanup_temp_files(temp_files)
            self.process = None

    def _cleanup_temp_files(self, temp_files: List[str]):
        """Remove arquivos temporários de forma segura"""
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logging.debug(f"Arquivo temporário removido: {file_path}")
                except OSError as e:
                    logging.warning(f"Falha ao remover arquivo temporário {file_path}: {e}")

    def _generate_all_ass_lines(self, tracks: List[Dict]):
        all_lines, all_styles = [], set()

        for i, track_data in enumerate(tracks):
            srt_path, effect_name = track_data["srt_path_var"].get(), track_data["effect_var"].get()

            effect_class = self.effect_classes.get(effect_name)

            if not srt_path or not effect_class or effect_name == "Nenhum":
                continue

            try:
                with open(srt_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                try:
                    with open(srt_path, 'r', encoding='latin1') as f:
                        content = f.read()
                except Exception as e:
                    logging.error(f"Não foi possível decodificar o arquivo SRT: {srt_path} - Erro: {e}")
                    continue

            # CORREÇÃO: Usando constante para espaçamento de camadas
            effect, config, base_layer = effect_class(), track_data["config"], i * LAYERS_PER_TRACK

            try:
                subtitles = list(srt.parse(content))
                logging.info(f"Processando {len(subtitles)} legendas da faixa {i+1} com o efeito '{effect_name}'")

                if hasattr(effect, 'generate_for_entire_track'):
                    logging.info(f"Efeito '{effect_name}' é cumulativo. Usando lógica de geração especial.")
                    if track_lines := effect.generate_for_entire_track(subtitles, base_layer, config):
                        all_lines.extend(track_lines)
                else:
                    for sub in subtitles:
                        if line := effect.generate_ass_line(sub, base_layer, config):
                            all_lines.append(line)

                all_styles.update(effect.required_styles)

            except Exception as e:
                logging.error(f"Erro ao processar SRT da faixa {i+1}: {e}")
                continue

        return all_lines, all_styles

    # CORREÇÃO: Nova função auxiliar para escapar caminhos de forma robusta
    def _escape_ffmpeg_filter_path(self, path: str) -> str:
        """Escapa um caminho de arquivo para ser usado com segurança em filtros do FFmpeg."""
        if os.name == 'nt':
            # No Windows, escape barras invertidas e dois pontos
            path = path.replace('\\', '\\\\').replace(':', '\\:')
        # Para todos os sistemas, escape caracteres especiais de filtro
        return path.replace("'", "'\\\\\\''").replace(",", "\\,")

    def _build_ffmpeg_command(self, vid_in, ass_path, quality_key, limit_duration, encoder_type: str) -> List[str]:
        base, _ = os.path.splitext(vid_in)
        output_file = f"{base}_legendado.mp4"

        # CORREÇÃO: Usando a nova função de escape
        escaped_ass_path = self._escape_ffmpeg_filter_path(ass_path)

        command = [self._get_executable('ffmpeg'), '-y', '-i', vid_in]

        if limit_duration:
            command.extend(['-t', str(limit_duration)])

        command.extend(['-vf', f"ass='{escaped_ass_path}'"])

        # --- LÓGICA DE HARDWARE (Baseada no seu Editor PiP v8/v9) ---
        crf_val = int(QUALIDADE_MAP[quality_key]) # Pega o valor numérico (ex: 23)
        enc_lower = encoder_type.lower()

        # Ajuste de qualidade para GPU (GPUs usam escalas diferentes do x264)
        # Geralmente somar um pouco ao CRF mantém o tamanho de arquivo similar
        gpu_quality = max(20, min(crf_val + 5, 35))

        if enc_lower == 'nvidia':
            command.extend([
                '-c:v', 'h264_nvenc',
                '-preset', 'p4',       # Equilibrado
                '-rc', 'constqp',      # Controle de qualidade constante
                '-cq', str(gpu_quality),
                '-pix_fmt', 'yuv420p'
            ])
        elif enc_lower == 'amd':
            command.extend([
                '-c:v', 'h264_amf',
                '-usage', 'ultrafast',
                '-rc', 'cqp',
                '-qp_p', str(gpu_quality),
                '-qp_i', str(gpu_quality),
                '-pix_fmt', 'yuv420p'
            ])
        elif enc_lower == 'intel':
            command.extend([
                '-c:v', 'h264_qsv',
                '-global_quality', str(gpu_quality),
                '-pix_fmt', 'nv12' # Intel QSV prefere NV12
            ])
        else: # CPU
            command.extend([
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', str(crf_val),
                '-pix_fmt', 'yuv420p'
            ])
        # -----------------------------------------------------------

        command.extend(['-c:a', 'copy', output_file])
        return command

    def generate_preview_clip(self, video_path: str, subtitle: srt.Subtitle, effect, config: Dict, base_layer: int) -> Optional[str]:
        ass_file_path = ""
        try:
            if not os.path.exists(video_path): raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {video_path}")
            if not subtitle: raise ValueError("Legenda não fornecida")

            video_info = self.get_video_info(video_path)
            if not video_info: raise RuntimeError("Não foi possível obter informações do vídeo para o preview.")

            video_duration = video_info['duration']
            subtitle_start_abs = subtitle.start.total_seconds()
            subtitle_end_abs = subtitle.end.total_seconds()
            clip_start_sec = max(0, subtitle_start_abs - 0.5)

            dialogue_lines = []

            if hasattr(effect, 'generate_for_entire_track'):
                new_start_rel = timedelta(seconds=max(0, subtitle_start_abs - clip_start_sec))
                new_end_rel = timedelta(seconds=max(0, subtitle_end_abs - clip_start_sec))

                preview_sub_for_cumulative = srt.Subtitle(
                    index=subtitle.index, start=new_start_rel, end=new_end_rel, content=subtitle.content
                )

                if generated_lines := effect.generate_for_entire_track([preview_sub_for_cumulative], base_layer, config):
                    dialogue_lines.extend(generated_lines)
            else:
                new_start_relative = timedelta(seconds=max(0, subtitle_start_abs - clip_start_sec))
                new_end_relative = timedelta(seconds=max(0, subtitle_end_abs - clip_start_sec))
                preview_subtitle = srt.Subtitle(
                    index=subtitle.index, start=new_start_relative, end=new_end_relative,
                    content=subtitle.content, proprietary=subtitle.proprietary
                )
                if line := effect.generate_ass_line(preview_subtitle, base_layer, config):
                    dialogue_lines.append(line)

            if not dialogue_lines:
                logging.warning("Efeito não gerou linha de diálogo para o preview.")
                return None

            final_dialogue_block = "\n".join(dialogue_lines)

            required_styles = set(effect.required_styles)
            style_block = "\n".join(ASS_STYLES[style_name] for style_name in sorted(list(required_styles)) if style_name in ASS_STYLES)

            # CORREÇÃO: Adotada resolução dinâmica para o cabeçalho do ASS no preview
            ass_header = ASS_HEADER_TEMPLATE.format(width=video_info['width'], height=video_info['height'])

            ass_content = (
                f"{ass_header}{style_block}\n\n[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                f"{final_dialogue_block}"
            )
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ass', encoding='utf-8') as temp_ass:
                temp_ass.write(ass_content)
                ass_file_path = temp_ass.name

            subtitle_duration = subtitle_end_abs - subtitle_start_abs
            min_duration, max_duration, preferred_duration = 3, 8, subtitle_duration + 1.5
            duration = max(min_duration, min(max_duration, preferred_duration))
            if clip_start_sec + duration > video_duration:
                duration = max(min_duration, video_duration - clip_start_sec)

            logging.info(f"Preview: cortando vídeo em {clip_start_sec:.1f}s por {duration:.1f}s.")

            temp_dir = tempfile.gettempdir()
            unique_filename = f"preview_{uuid.uuid4().hex[:8]}.mp4"
            output_clip_path = os.path.join(temp_dir, unique_filename)

            # CORREÇÃO: Usando a nova função de escape
            escaped_ass_path = self._escape_ffmpeg_filter_path(ass_file_path)
            video_filters = f"scale=-2:720,ass='{escaped_ass_path}'"

            command = [
                self._get_executable('ffmpeg'), '-y', '-ss', str(clip_start_sec), '-i', video_path,
                '-t', str(duration), '-vf', video_filters, '-c:v', 'libx264', '-preset', 'ultrafast',
                '-crf', '28', '-pix_fmt', 'yuv420p', '-an', output_clip_path
            ]
            logging.info(f"Comando preview FFmpeg: {' '.join(command)}")

            # CORREÇÃO: Adicionado timeout para evitar travamentos no preview
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)

            if os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 0:
                logging.info(f"Clipe de preview gerado com sucesso: {output_clip_path}")
                return output_clip_path
            else:
                raise RuntimeError("Arquivo de preview gerado está vazio ou não existe")

        except subprocess.TimeoutExpired as e:
            error_msg = "O FFmpeg demorou demais para gerar o preview (timeout)."
            logging.error(f"{error_msg}\nComando: {' '.join(e.cmd)}")
            return None
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else 'Erro desconhecido'
            logging.error(f"Erro do FFmpeg no preview:\nComando: {' '.join(e.cmd)}\nSaída de erro:\n{error_msg}")
            return None
        except Exception as e:
            logging.error(f"Falha ao gerar clipe de preview: {e}\n{traceback.format_exc()}")
            return None
        finally:
            if ass_file_path and os.path.exists(ass_file_path):
                try: os.remove(ass_file_path)
                except OSError: pass

    def _monitor_progress(self, total_duration: float):
        if not self.process or not self.process.stderr: return
        for line in self.process.stderr:
            if match := re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line):
                h, m, s, ms = map(int, match.groups())
                current_time = h * 3600 + m * 60 + s + ms / 100
                progress = min(current_time / total_duration, 1.0)
                self.progress_queue.put(('progress', progress))
            if "error" in line.lower() or "failed" in line.lower():
                logging.warning(f"FFmpeg warning/error: {line.strip()}")
