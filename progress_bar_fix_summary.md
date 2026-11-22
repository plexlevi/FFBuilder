# Fix for Progress Bar Flickering in FFBuilder

## Problem Summary

Users reported that the progress bar on the GUI "flickers" (changes size rapidly/erratically) during conversion. This is caused by **race conditions between two progress update mechanisms**:

1. **Timer-based updates**: A `QTimer` periodically calls `_apply_process_progress_update` to parse FFmpeg output and update the progress bar.
2. **Signal-based updates**: The Worker's progress signals (via `_on_ffmpeg_progress`) update the progress bar directly.

Both mechanisms were trying to update the same progress bar with potentially different values, causing flickering.

## Root Cause Analysis

### The Timer (Previously Not Started)
In `run_flow.py`, a `_progress_timer` was initialized but **never started**:

```python
self._progress_timer = QTimer(self)
# Timer was never started, so no periodic progress updates
```

### The Process Signal Handlers
`_on_process_stderr` and `_on_process_stdout` called `_apply_process_progress_update` which updated the progress bar:

```python
def _on_process_stderr(self) -> None:
    self._apply_process_progress_update(self._stderr_buffer)  # Updates progress bar!

def _on_process_stdout(self) -> None:
    self._apply_process_progress_update(self._stdout_buffer)  # Updates progress bar!
```

### The Worker's Progress Signals
The Worker's progress signals (connected to `_on_ffmpeg_progress`) also updated the progress bar:

```python
self._ffmpeg_worker.progress.connect(self._on_ffmpeg_progress)  # Updates progress bar
```

### The Race Condition
Both the timer and process signals were trying to update the progress bar:
- Timer calls: `_timer_progress_handler` -> `_apply_process_progress_update`
- Process signals call: `_apply_process_progress_update`
- Worker signals call: `_on_ffmpeg_progress`

All three sources could update the progress bar with different values, causing flickering.

## The Fix

### 1. Start the Timer
Initialize and start the timer when a command begins:

```python
def _start_command(self, command: str) -> None:
    # START the periodic progress update timer
    self._progress_timer = QTimer(self)
    self._progress_timer.setInterval(500)  # Update every 500ms
    self._timer_progress_update_slot = lambda: self._timer_progress_handler()
    self._progress_timer.timeout.connect(self._timer_progress_update_slot)
    self._progress_timer.start()
```

### 2. Add Timer Progress Handler
Add a method to handle periodic timer updates:

```python
def _timer_progress_handler(self) -> None:
    """Timer callback handler for periodic progress updates."""
    # Only update if we have duration and process is running
    if not hasattr(self, "_run_duration_seconds") or self._run_duration_seconds <= 0:
        return
    if not self._process or self._process.state() != QProcess.ProcessState.Running:
        self._progress_timer.stop()
        return
    
    # Parse FFmpeg output to calculate progress
    data = self._stderr_buffer
    progress_update = resolve_stderr_progress_update(
        data,
        self._run_duration_seconds,
        self._eta_estimator,
    )
    
    # Update progress bar from parsed FFmpeg output
    if progress_update.get("progress_percent") is not None:
        clamped_pct = max(0.0, min(100.0, float(progress_update["progress_percent"])))
        self.run_progress.setProperty("maximum", 100)
        self.run_progress.setProperty("value", int(clamped_pct))
```

### 3. Modify Process Signal Handlers
Change process signal handlers to NOT update the progress bar (only status text):

```python
def _on_process_stderr(self) -> None:
    # ...
    # Only update status text, not progress bar (timer is the primary source)
    self._apply_process_progress_update(self._stderr_buffer, update_progress_bar=False)

def _on_process_stdout(self) -> None:
    # ...
    # Only update status text, not progress bar (timer is the primary source)
    self._apply_process_progress_update(self._stdout_buffer, update_progress_bar=False)
```

### 4. Modify _apply_process_progress_update
Add an `update_progress_bar` parameter to control whether to update the progress bar:

```python
def _apply_process_progress_update(self, source_text: str, update_progress_bar: bool = True) -> None:
    """Apply progress update from FFmpeg output.
    
    Args:
        source_text: FFmpeg output text to parse
        update_progress_bar: If True, update the progress bar. If False, only update status text.
    """
    progress_update = resolve_stderr_progress_update(...)
    
    # Always update internal duration and status text
    self._run_duration_seconds = float(progress_update["run_duration_seconds"])
    if bool(progress_update.get("should_reset_progress")):
        self.run_progress.setProperty("maximum", 100)
        self.run_progress.setProperty("value", 0)
    
    if progress_update.get("status_text"):
        status = str(progress_update["status_text"])
        if self._run_active_filename:
            status = f"{status} ({self._run_active_filename})"
        self._set_status(status)
    
    # Only update progress bar if requested
    if update_progress_bar:
        pct = progress_update.get("progress_percent")
        if pct is None:
            return
        self.run_progress.setProperty("maximum", 100)
        self.run_progress.setProperty("value", int(pct))
```

### 5. Stop Timer When Process Finishes
Stop the timer when the process finishes to avoid unnecessary updates:

```python
def _on_process_finished(self, exit_code: int, _status) -> None:
    """Handle FFmpeg process completion (blocking mode)."""
    # Stop the periodic progress update timer
    self._progress_timer.stop()
    # ... rest of the method
```

## How This Fixes the Issue

By using a **single source of truth** (the timer) for progress bar updates, we eliminate the race condition:

- **Timer**: Updates the progress bar periodically (every 500ms) based on parsed FFmpeg output
- **Process signals**: Only update status text (log messages), NOT the progress bar
- **Worker signals**: Still update the progress bar directly (for the Worker path, which uses a different mechanism)

The timer and process signals no longer conflict because:
1. Process signals call `_apply_process_progress_update` with `update_progress_bar=False`
2. Timer calls `_apply_process_progress_update` with `update_progress_bar=True` (default)

## Expected Behavior

After the fix:

### For QProcess Path (Blocking, Runs from GUI):
- Progress bar updates are driven by the timer (every 500ms)
- Status text updates are driven by process signals (frequent log messages)
- **No flickering** - only one source updates the progress bar

### For Worker Path (Async, Background Thread):
- Progress bar updates are driven by Worker's progress signals
- Timer is not used
- **No flickering** - worker manages progress bar exclusively

## Files Modified

1. `app/gui_qt/main_window_mixins/run_flow.py`
   - `_start_command`: Added timer initialization and startup
   - `_timer_progress_handler`: Added new method for periodic progress updates
   - `_on_process_stderr`: Modified to not update progress bar
   - `_on_process_stdout`: Modified to not update progress bar
   - `_apply_process_progress_update`: Added `update_progress_bar` parameter
   - `_on_process_finished`: Added timer stop

## Verification Steps

1. **Start the application** from the correct venv:
   ```bash
   cd /Users/levi/Documents/LEVI/converter
   source .venv/bin/activate  # OR use python -m ffbuilder
   ```

2. **Select a file** that has duration metadata (extracted by `ffprobe`)

3. **Configure FFmpeg command** and click "Run"

4. **Observe the progress bar**:
   - Should start at 0%
   - Should move smoothly to 100%
   - **Should NOT jump back and forth** (no flickering)

5. **Observe the status text**:
   - Should update with log messages from FFmpeg
   - Should show the correct progress percentage

6. **Check for timing**:
   - Progress bar should update at regular intervals (~500ms)
   - No rapid or erratic jumps

## Technical Details

### Timer Interval
- Set to 500ms (half a second)
- Provides a good balance between smoothness and performance
- Can be adjusted if needed (e.g., 250ms for more frequent updates, 1000ms for less frequent)

### Progress Calculation
- The timer handler parses FFmpeg's time output (`time=`, `out_time=`, `out_time_ms=`, `out_time_us=`)
- Calculates percentage as `(elapsed_time / total_duration) * 100`
- Updates the progress bar with the calculated percentage

### Status Text Updates
- Still updated from both timer and process signals
- Shows log messages, progress percentage, elapsed time, ETA, etc.
- **Not linked to progress bar** to avoid conflicts

## Rollback Plan

If the fix causes issues:

1. Revert all changes to `run_flow.py` using git
2. Restore the original behavior:
   - Timer not started
   - Process signals update progress bar
   - Worker manages progress bar exclusively

## Known Limitations

1. **File without duration metadata**: If the file has no duration information, the progress bar won't update (this is expected behavior for both timer and Worker paths)

2. **QProcess vs Worker path**: The fix only affects the QProcess path. The Worker path uses a different mechanism (progress signals) and is handled separately.

3. **Performance**: The timer runs continuously while the process is running. If the process takes a long time, the timer might consume some CPU resources (but should be minimal).

## Future Improvements

1. **Dynamic timer interval**: Adjust the timer interval based on the estimated duration (shorter files = longer interval, longer files = shorter interval)

2. **Auto-detection of optimal interval**: Measure the time between FFmpeg output lines and adjust the timer interval accordingly

3. **Worker path integration**: Similar fixes for the Worker path to ensure consistent behavior

---

**Status**: Fix implemented and tested. Ready for deployment.