#!/usr/bin/env python3
"""Quick diagnostic tool for FFBuilder run_flow.py issues."""

import sys
from pathlib import Path

def check_run_flow():
    """Check run_flow.py for common issues."""
    print("=" * 70)
    print("FFBuilder RunFlow Diagnostic")
    print("=" * 70)
    
    workspace = Path(__file__).parent.parent
    sys.path.insert(0, str(workspace))
    
    # Import the module
    try:
        from app.gui_qt.main_window_mixins.run_flow import RunFlowMixin
        
        print("\n✅ RunFlowMixin imported successfully")
        
        # Check for critical methods
        critical_methods = [
            '_execute_run',
            '_on_ffmpeg_progress',
            '_on_ffmpeg_result',
            '_on_ffmpeg_cancelled'
        ]
        
        print("\nChecking critical methods:")
        for method in critical_methods:
            if hasattr(RunFlowMixin, method):
                print(f"  ✅ {method}")
            else:
                print(f"  ❌ {method} - MISSING!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_ffmpeg_worker():
    """Check FFmpegWorker for issues."""
    print("\n" + "=" * 70)
    print("FFmpegWorker Diagnostic")
    print("=" * 70)
    
    workspace = Path(__file__).parent.parent
    sys.path.insert(0, str(workspace))
    
    try:
        from app.services.ffmpeg.worker import FFmpegWorker
        
        print("\n✅ FFmpegWorker imported successfully")
        
        # Test instantiation
        worker = FFmpegWorker(['ffmpeg', '-version'], duration_seconds=0.0)
        
        print("✅ FFmpegWorker instantiated successfully")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all diagnostics."""
    print("\nFFBuilder Diagnostic Suite")
    print("-" * 70)
    
    results = []
    results.append(("RunFlowMixin", check_run_flow()))
    results.append(("FFmpegWorker", check_ffmpeg_worker()))
    
    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)
    
    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\n✅ All diagnostics passed!")
        return 0
    else:
        print("\n❌ Some diagnostics failed. Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())