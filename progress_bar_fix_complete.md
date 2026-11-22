# Progress Bar Fix - Complete Solution

## Problem
The green progress bar was not showing any progress during file conversion, even though the status text was updating correctly.

## Root Cause
When `duration_seconds == 0`, the FFmpegWorker was setting `_progress_disabled = True`, which prevented it from emitting any progress signals. The GUI's progress bar depends on these signals, so it never updated.

## Solution

### Fix 1: Always Set Progress Bar Maximum to 100
**File**: `app/gui_qt/main_window_parts/process_flow.py`

**Before**:
```python
def init_run_progress_display(progress_bar: QProgressBar, duration_seconds: float) -> None:
    if duration_seconds > 0:
        progress_bar.setProperty("maximum", 100)
        progress_bar.setProperty("value", 0)
    else:
        progress_bar.setProperty("maximum", 0)  # PROBLEM: bar never shows progress
        progress_bar.setProperty("value", 0)
    progress_bar.setVisible(True)
```

**After**:
```python
def init_run_progress_display(progress_bar: QProgressBar, duration_seconds: float) -> None:
    # IMPORTANT: Always set maximum to 100 to enable progress bar visualization
    progress_bar.setProperty("maximum", 100)
    progress_bar.setProperty("value", 0)
    progress_bar.setVisible(True)
```

### Fix 2: Worker Auto-Detects Duration from FFmpeg Output
**File**: `app/services/ffmpeg/worker.py`

**Changes**:
1. Replace `_progress_disabled` flag with `auto_detecting_duration` flag
2. When `duration_seconds == 0`, the worker will try to extract duration from the first FFmpeg `-progress` output line
3. Once duration is detected, it's locked and won't change

**Key Logic**:
```python
# Instead of disabling progress when duration=0
if not self.detect_duration and self.duration_seconds == 0:
    self.auto_detecting_duration = True  # Track auto-detection phase

def _emit_progress(self, progress_info: dict) -> None:
    # If progress is explicitly disabled, don't emit anything
    if getattr(self, '_progress_disabled', False):
        return
    
    if progress_info is None:
        return

    pct = progress_info.get("progress_percent")
    
    if pct is not None:
        # Auto-detect duration from FFmpeg output if not provided
        if self.auto_detecting_duration and self.duration_seconds == 0:
            duration = progress_info.get("duration_seconds")
            if duration is not None:
                self.duration_seconds = duration
                self.auto_detecting_duration = False  # Lock the duration
                # NOW we can calculate and emit progress
            else:
                # No duration yet, wait until we get it
                return
        
        if self.duration_seconds > 0:
            self.progress.emit(pct, f"{int(pct)}%")
```

### How It Works

1. **User starts conversion** with `duration_seconds = 0` (not provided)
2. **GUI initializes progress bar** with `maximum = 100`, `value = 0`
3. **Worker starts** and begins reading FFmpeg output
4. **First Progress line appears** in output (e.g., `Progress: 0.1% time=00:00:00.00`)
5. **Worker extracts duration** from the first Progress line (e.g., 3.0 seconds)
6. **Worker locks duration** (won't change anymore)
7. **Worker starts emitting progress** signals (0.1%, 0.2%, 0.3%, ...)
8. **GUI updates progress bar** smoothly from 0% to 100%
9. **Status text updates** from log parsing (no flickering)

### Expected FFmpeg -progress Output Format

```
Progress: 0.1%...
time=00:00:00.00, bitrate=1234.5kB/s
```

The worker parses:
- `Progress: XX%` → current progress percentage
- `time=HH:MM:SS` or `out_time=HH:MM:SS` → total duration

If the duration can be extracted from the first Progress line, the worker will:
1. Use the extracted duration for progress calculation
2. Lock the duration so it doesn't change
3. Start emitting progress signals

## Files Modified

1. `app/gui_qt/main_window_parts/process_flow.py` - `init_run_progress_display`
2. `app/services/ffmpeg/worker.py` - `_emit_progress` and initialization logic

## Testing Recommendation

1. Start FFBuilder
2. Load a file for conversion
3. Click "Run" without setting duration
4. Watch the green progress bar - it should:
   - Start at 0%
   - Begin moving after a few seconds (when first Progress line appears)
   - Continue moving smoothly to 100%
   - NOT flicker

## Additional Notes

- If FFmpeg doesn't output `-progress` info, the progress bar will stay at 0%
- In that case, you should provide an explicit duration or enable `-progress` in FFmpeg
- The status text (percentage in the status bar) still updates correctly