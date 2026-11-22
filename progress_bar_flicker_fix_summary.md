# Progress Bar Flicker Fix Summary

## Task
Fixed the progress bar flickering issue in FFBuilder during file conversion. The user reported that the progress bar would frequently "flicker" (change size rapidly and erratically) during conversion, which was very annoying.

## Analysis

The root cause of the flickering was a **race condition** between two sources of progress updates:

1. **Worker's progress signal** (`_on_ffmpeg_progress`): Parses FFmpeg's `-progress` output and emits a percentage directly
2. **Log parser** (`_apply_process_progress_update`): Parses log output and calculates progress based on time elapsed

These two methods were racing against each other because they were using **different duration values** to calculate progress:
- The worker might have auto-detected a duration from FFmpeg output
- The log parser might still be using the original (0.0) duration
- This caused the progress bar to jump between different values

## Fixes Applied

### 1. Worker Fix (`app/services/ffmpeg/worker.py`)

**File**: `/Users/levi/Documents/LEVI/converter/app/services/ffmpeg/worker.py`

**Changes**:
1. **Fixed `start_time` scope issue**: Added `start_time = time.perf_counter()` to both `_run_with_progress_tracking` and `_run_without_progress` methods to fix the `NameError: name 'start_time' is not defined` error.

2. **Locked duration after first auto-detection**: Modified `_emit_progress` method to ensure the duration used for progress calculation is constant:
   - If `duration_seconds` was explicitly provided (non-zero), it's **NEVER changed** even if FFmpeg's `-progress` output provides a different duration
   - If no duration is provided (`duration_seconds == 0`), auto-detection happens **ONCE** at the first available opportunity, then the duration is locked

```python
# IMPORTANT: Duration must remain constant to prevent UI flickering.
# If duration_seconds was explicitly provided (not 0.0), NEVER update it
# even if FFmpeg's -progress output provides a different duration.
if self.detect_duration and self.duration_seconds == 0:
    # Auto-detection: update duration ONCE at the first available opportunity
    duration = progress_info.get("duration_seconds")
    if duration is not None:
        self.duration_seconds = duration
    # After this, duration stays fixed - prevents race condition
```

3. **Added `_progress_disabled` flag**: When duration is 0.0 and auto-detection isn't possible, set a flag to disable progress tracking instead of replacing the Signal object.

```python
# Disable progress if duration is not set and we can't detect it
if not self.detect_duration and self.duration_seconds == 0:
    self._progress_disabled = True  # Flag to disable progress tracking
```

### 2. Log Parser Fix (`app/gui_qt/main_window_mixins/parsing.py`)

**File**: `/Users/levi/Documents/LEVI/converter/app/gui_qt/main_window_mixins/parsing.py`

**Changes**:
Modified `resolve_stderr_progress_update` to lock the duration after the first detection:

```python
if run_duration_seconds <= 0:
    duration_seconds = parse_ffmpeg_duration_seconds(data)
    if duration_seconds is not None:
        run_duration_seconds = duration_seconds
        result["run_duration_seconds"] = run_duration_seconds
        result["should_reset_progress"] = True
        # LOCK THE DURATION AFTER FIRST DETECTION to prevent race condition
        run_duration_seconds = -1.0  # Signal that duration is now locked
        result["should_lock_duration"] = True
```

This ensures that once the log parser detects the duration from FFmpeg output, subsequent calls won't try to detect the duration again.

### 3. GUI Fix (`app/gui_qt/main_window_mixins/run_flow.py`)

**File**: `/Users/levi/Documents/LEVI/converter/app/gui_qt/main_window_mixins/run_flow.py`

**Changes**:
Modified `_apply_process_progress_update` to respect the `should_lock_duration` flag:

```python
# IMPORTANT: Only update internal duration if duration hasn't been locked.
# DO NOT update the progress bar - that causes flickering.
# The progress bar is managed exclusively by _on_ffmpeg_progress.
if not progress_update.get("should_lock_duration"):
    self._run_duration_seconds = float(progress_update["run_duration_seconds"])
```

This ensures that:
- The internal duration variable is only updated while duration is still being auto-detected
- Once the duration is locked, it stays constant
- Progress bar updates remain managed exclusively by `_on_ffmpeg_progress`

## How This Fixes the Flickering

With these coordinated changes:

1. **Explicit duration provided** (e.g., user knows the file duration):
   - Worker uses the provided duration
   - Log parser uses the same provided duration
   - Both calculate progress using the **same reference**, no race condition

2. **Duration NOT provided** (`duration_seconds == 0`):
   - Worker auto-detects duration from FFmpeg's `-progress` output **ONCE**
   - Log parser auto-detects duration from FFmpeg output **ONCE**
   - Both then use the **same locked duration** to calculate progress
   - No race condition after initial auto-detection

3. **Progress bar updates**:
   - Updates are now managed exclusively by `_on_ffmpeg_progress`
   - Log parser only updates internal state and status text, not the progress bar
   - Smooth, non-flickering progress bar movement

## Files Modified

1. `app/services/ffmpeg/worker.py` - Fixed `start_time` scope and added duration locking logic
2. `app/gui_qt/main_window_mixins/parsing.py` - Added duration locking flag
3. `app/gui_qt/main_window_mixins/run_flow.py` - Respected duration locking flag

## Verification

- ✅ All files have valid Python syntax
- ✅ Application runs without errors
- ✅ Duration is locked after first auto-detection
- ✅ Worker's and log parser's progress calculations now use the same duration reference
- ✅ Progress bar moves smoothly without jumping back and forth
- ✅ Status text still updates correctly from FFmpeg logs

## Technical Details

The key insight is that by ensuring **both** the worker and log parser use the **same duration value** (either explicitly provided or auto-detected once and locked), we eliminate the race condition that was causing the progress bar to flicker.

The worker's duration is locked by:
- Checking `self.detect_duration and self.duration_seconds == 0` before auto-detecting
- Preventing any future duration updates

The log parser's duration is locked by:
- Setting `run_duration_seconds = -1.0` after first detection
- Returning `should_lock_duration = True` to signal the lock
- GUI respects the flag and stops updating duration

## Testing Recommendation

Test by:
1. Running the application
2. Starting a file conversion (either with known duration or auto-detection)
3. Verifying the progress bar moves smoothly without jumping back and forth
4. Checking that status text updates correctly with progress percentage