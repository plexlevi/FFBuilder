"""FFmpegWorker - Asynchronous FFmpeg process execution using QThread."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import List, Optional

from PySide6.QtCore import QThread, Signal, QTimer


class FFmpegWorker(QThread):
    """
    Run a complete FFmpeg argv list in a background thread.

    The worker must receive the full command (program + all arguments), including
    input/output paths. It must not reconstruct or append paths itself.

    IMPORTANT: The worker parses duration from FFmpeg's -progress output and uses it
    for progress calculation. This ensures consistency with the log parser and
    prevents UI flickering.
    """

    progress = Signal(float, str)  # percentage (0-100), message
    log_output = Signal(str)       # raw output chunks for console / error dialogs
    result = Signal(dict)          # {status, output, error, duration, exit_code}
    cancelled = Signal()

    def __init__(
        self,
        argv: List[str],
        *,
        duration_seconds: float = -1.0,
    ):
        """
        Initialize the worker.

        Args:
            argv: Full FFmpeg command as a list of strings (program + arguments).
            duration_seconds: The expected total duration of the output in seconds.
                              Use -1.0 to auto-detect from FFmpeg output.
                              Use 0.0 to enable auto-detection from FFmpeg output.
                              Use a positive value to use that exact duration.

        NOTE:
            If duration_seconds is -1.0 or 0.0, the worker will try to detect duration
            from FFmpeg's -progress output line. Detection happens ONCE at the first
            available Progress line, then the duration is locked for the rest of
            conversion to prevent UI flickering.
        """
        super().__init__()
        self.argv = list(argv)
        # If duration is -1.0, we'll try to detect it from FFmpeg's output
        self.duration_seconds = float(duration_seconds or -1.0)  # Default to auto-detect
        self._auto_detected_duration = False  # Track if duration was auto-detected
        
        # DEBUG: Show initialization
        print(f"[DEBUG Worker] Initialized: duration={self.duration_seconds}, auto_detect={self._auto_detected_duration}, enabled={self._progress_enabled()}")
        self.cancelled_flag = False
        self._process: Optional[subprocess.Popen] = None
        self.logger = logging.getLogger(__name__)

        # Duration logic:
        # - If duration_seconds > 0: Use the provided duration for progress calculation.
        # - If duration_seconds < 0 (e.g., -1.0): Wait for user to set duration (progress disabled until then).
        # - Progress bar will only show meaningful progress when duration is set.

    def run(self) -> None:
        start_time = time.perf_counter()
        
        # DEBUG: Show run start
        print(f"[DEBUG Worker] Run started at {start_time}")

        if self.cancelled_flag:
            self.result.emit({
                "status": "cancelled",
                "output": None,
                "error": "Conversion cancelled by user",
                "duration": 0.0,
                "exit_code": None,
            })
            return

        if not self.argv:
            self.result.emit({
                "status": "error",
                "output": None,
                "error": "Empty FFmpeg command",
                "duration": 0.0,
                "exit_code": None,
            })
            return

        try:
            # Start FFmpeg process
            self._process = subprocess.Popen(
                self.argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            assert self._process.stdout is not None

            # DEBUG: Check progress enabled
            print(f"[DEBUG Worker] _progress_enabled() returned: {self._progress_enabled()}")
            
            if self._progress_enabled():
                # Use -progress output for real-time progress tracking
                self._run_with_progress_tracking()
            else:
                # No progress tracking
                self._run_without_progress()

        except FileNotFoundError:
            self.result.emit({
                "status": "error",
                "output": None,
                "error": "FFmpeg binary not found. Please install FFmpeg.",
                "duration": time.perf_counter() - start_time,
                "exit_code": None,
            })
        except Exception as e:
            self.logger.error("Unexpected FFmpeg worker error: %s", e, exc_info=True)
            self.result.emit({
                "status": "error",
                "output": None,
                "error": f"Unexpected FFmpeg error: {e}",
                "duration": time.perf_counter() - start_time,
                "exit_code": None,
            })
        finally:
            self._process = None

    def _progress_enabled(self) -> bool:
        """Check if progress tracking is enabled."""
        return self._auto_detected_duration or self.duration_seconds > 0

    def _run_with_progress_tracking(self) -> None:
        """
        Run FFmpeg with real-time progress tracking.

        This method reads FFmpeg's -progress output and emits progress updates.
        The duration is parsed from the Progress line output.
        """
        start_time = time.perf_counter()
        output_buffer: list[str] = []

        try:
            self._process = subprocess.Popen(
                self.argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            assert self._process.stdout is not None

            while True:
                if self.cancelled_flag:
                    self._terminate_process()
                    self.cancelled.emit()
                    self.result.emit({
                        "status": "cancelled",
                        "output": "".join(output_buffer),
                        "error": "Conversion cancelled by user",
                        "duration": time.perf_counter() - start_time,
                        "exit_code": self._process.poll(),
                    })
                    return

                line = self._process.stdout.readline()
                if not line:
                    break

                output_buffer.append(line)
                self.log_output.emit(line)

                # Check for Progress: line
                full_output = "\n".join(output_buffer)
                
                # DEBUG: Log when we see a Progress line
                if "Progress:" in full_output:
                    # Parse duration and current time from the Progress line
                    progress_info = self._parse_progress_line(full_output)
                    print(f"[DEBUG Worker] Found Progress line: {progress_info.get('progress_percent', 'N/A')}%, duration={progress_info.get('duration_seconds', 'NOT_FOUND') if progress_info else 'PARSE_FAILED'}")
                    if progress_info is not None:
                        self._emit_progress(progress_info)

            self._process.wait()
            duration = time.perf_counter() - start_time
            exit_code = self._process.returncode
            output_text = "".join(output_buffer)

            if self.cancelled_flag:
                self.cancelled.emit()
                self.result.emit({
                    "status": "cancelled",
                    "output": output_text,
                    "error": "Conversion cancelled by user",
                    "duration": duration,
                    "exit_code": exit_code,
                })
                return

            if exit_code == 0:
                self.logger.info("FFmpeg conversion successful")
                self.result.emit({
                    "status": "success",
                    "output": output_text,
                    "error": None,
                    "duration": duration,
                    "exit_code": 0,
                })
            else:
                error_tail = output_text.strip() or "(no FFmpeg output captured)"
                if len(error_tail) > 4000:
                    error_tail = error_tail[-4000:]
                self.logger.error(
                    "FFmpeg conversion failed (exit code %s): %s",
                    exit_code,
                    error_tail[:200],
                )
                self.result.emit({
                    "status": "error",
                    "output": output_text,
                    "error": f"FFmpeg error (exit code {exit_code}):\n{error_tail}",
                    "duration": duration,
                    "exit_code": exit_code,
                })

        except Exception as e:
            self.logger.error("Error running FFmpeg: %s", e)
            self.result.emit({
                "status": "error",
                "output": None,
                "error": f"FFmpeg error: {e}",
                "duration": time.perf_counter() - start_time,
                "exit_code": -1,
            })

    def _run_without_progress(self) -> None:
        """Run FFmpeg without progress tracking (blocking mode)."""
        start_time = time.perf_counter()
        try:
            self._process = subprocess.Popen(
                self.argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            while True:
                if self.cancelled_flag:
                    self._terminate_process()
                    break
                line = self._process.stdout.readline()
                if not line:
                    break
                self.log_output.emit(line)

            self._process.wait()
            exit_code = self._process.returncode

            self.result.emit({
                "status": "success" if exit_code == 0 else "error",
                "output": "",
                "error": None if exit_code == 0 else "FFmpeg error",
                "duration": time.perf_counter() - start_time,
                "exit_code": exit_code,
            })
        except Exception as e:
            self.logger.error("Error running FFmpeg: %s", e)
            self.result.emit({
                "status": "error",
                "output": None,
                "error": f"FFmpeg error: {e}",
                "duration": time.perf_counter() - start_time,
                "exit_code": -1,
            })

    def cancel(self) -> None:
        """Request cancellation; terminates the running FFmpeg process if any."""
        self.cancelled_flag = True
        self._terminate_process()

    def _terminate_process(self) -> None:
        """Terminate the FFmpeg process."""
        proc = self._process
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass

    def _parse_progress_line(self, output_text: str) -> Optional[dict]:
        """
        Parse the Progress line from FFmpeg output.

        Args:
            output_text: The complete FFmpeg output (from start to now).

        Returns:
            dict with keys: progress_percent, duration_seconds, current_time, or None
        """
        # Find the last Progress line
        lines = output_text.splitlines()
        for line in reversed(lines):
            if "Progress:" in line:
                # Parse the progress line
                prog = self._parse_progress_line_content(line)
                # Extract duration from the Progress line (second time value)
                duration = self._parse_duration(line)
                return prog if duration is not None else None

        return None

    def _parse_progress_line_content(self, line: str) -> Optional[dict]:
        """Parse progress percentage and message from a Progress line."""
        match = re.search(r"Progress: (\d+)%", line)
        if match:
            try:
                pct = int(match.group(1))
                return {"progress_percent": max(0.0, min(100.0, float(pct)))}
            except (ValueError, AttributeError):
                pass
        return None

    def _parse_duration(self, line: str) -> Optional[float]:
        """
        Parse duration from a FFmpeg line.

        Looks for time= or out_time= patterns in the line.
        """
        # Try time= pattern first
        match = re.search(r"time=(\d{2}):(\d{2}):(\d+(?:\.\d+)?)", line)
        if match:
            hh, mm, ss = match.groups()
            return float(hh) * 3600 + float(mm) * 60 + float(ss)

        # Try out_time= pattern
        match = re.search(r"out_time=(\d{2}):(\d{2}):(\d+(?:\.\d+)?)", line)
        if match:
            hh, mm, ss = match.groups()
            return float(hh) * 3600 + float(mm) * 60 + float(ss)

        return None

    def _emit_progress(self, progress_info: dict) -> None:
        """Emit progress update to the UI."""
        # DEBUG: Show when _emit_progress is called
        if progress_info is not None:
            print(f"[DEBUG Worker._emit_progress] Called with progress_info: {progress_info}")
        
        if progress_info is None:
            return

        # Try to parse current time from all accumulated FFmpeg output
        current = self._progress_from_text(self._output_buffer)
        
        if current is None:
            return

        # If we have both current time and duration, emit progress
        # DEBUG: Check if we can calculate progress
        if self.duration_seconds > 0:
            print(f"[DEBUG Worker._emit_progress] duration={self.duration_seconds}, will emit progress")
            pct = max(0.0, min(100.0, (current / self.duration_seconds) * 100))
            self.progress.emit(pct, f"{int(pct)}%")
        elif not self._auto_detected_duration and progress_info.get("duration_seconds") is not None:
            # Auto-detect duration from FFmpeg output and lock it
            print(f"[DEBUG Worker._emit_progress] Auto-detecting duration: {progress_info['duration_seconds']}s")
            new_duration = progress_info["duration_seconds"]
            self.duration_seconds = new_duration
            self._auto_detected_duration = True
            # Now we have duration, emit progress
            pct = max(0.0, min(100.0, (current / self.duration_seconds) * 100))
            print(f"[DEBUG Worker._emit_progress] Emitted progress: {pct}%")
            self.progress.emit(pct, f"{int(pct)}%")

    def _progress_from_text(self, text: str) -> Optional[float]:
        """
        Calculate progress percentage from FFmpeg output text.
        Uses self.duration_seconds as the reference duration.
        """
        if self.duration_seconds <= 0:
            return None

        current = None

        # Try out_time_ms (from -progress)
        ms_matches = _OUT_TIME_MS_RE.findall(text)
        if ms_matches:
            try:
                current = float(ms_matches[-1]) / 1_000_000.0
            except ValueError:
                pass

        if current is None:
            # Try out_time_us (from -progress)
            us_matches = _OUT_TIME_US_RE.findall(text)
            if us_matches:
                try:
                    current = float(us_matches[-1]) / 1_000_000.0
                except ValueError:
                    pass

        if current is None:
            # Try out_time or time
            for regex in [_OUT_TIME_RE, _TIME_RE]:
                matches = regex.findall(text)
                if matches:
                    hh, mm, ss = matches[-1]
                    current = int(hh) * 3600 + int(mm) * 60 + float(ss)
                    break

        if current is None:
            return None

        return max(0.0, min(100.0, (current / self.duration_seconds) * 100.0))


def convert_file_async(argv: List[str], duration_seconds: float = 0.0) -> FFmpegWorker:
    """Create and start an async FFmpeg conversion for the given full argv."""
    worker = FFmpegWorker(argv, duration_seconds=duration_seconds)
    worker.start()
    return worker


# Regex patterns for FFmpeg output
_OUT_TIME_MS_RE = re.compile(r"out_time_ms=(\d+)")
_OUT_TIME_US_RE = re.compile(r"out_time_us=(\d+)")
_OUT_TIME_RE = re.compile(r"out_time=(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")
_TIME_RE = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")