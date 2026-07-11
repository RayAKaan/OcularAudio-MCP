import time
import sys
import asyncio
import os
import json

# Test URLs
SHORT_VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - 3:33
LONG_VIDEO = "https://www.youtube.com/watch?v=aircAruvnKk"  # 3Blue1Brown - Neural Networks - 19:47

async def benchmark_whisper():
    """Benchmark Whisper transcription (downloads audio + transcribes)."""
    from ocular_audio_mcp import _blocking_whisper_transcription, find_cookies_file
    cookies = find_cookies_file()
    
    print("  Downloading audio and transcribing with Whisper...")
    start = time.perf_counter()
    try:
        result = await asyncio.to_thread(
            _blocking_whisper_transcription, 
            "dQw4w9WgXcQ", 
            cookies
        )
        elapsed = time.perf_counter() - start
        return elapsed, len(result)
    except Exception as e:
        elapsed = time.perf_counter() - start
        return elapsed, f"Error: {e}"

async def benchmark_multiple_screenshots():
    """Benchmark capturing multiple screenshots."""
    from ocular_audio_mcp import get_ocular_audio_video_screenshots
    
    timestamps = [10, 30, 60, 90, 120]  # 5 screenshots
    start = time.perf_counter()
    result = await get_ocular_audio_video_screenshots(SHORT_VIDEO, timestamps_secs=timestamps)
    elapsed = time.perf_counter() - start
    
    success_count = sum(1 for item in result if hasattr(item, 'path'))
    return elapsed, success_count, len(timestamps)

async def benchmark_context_auto():
    """Benchmark the full context tool in auto mode."""
    from ocular_audio_mcp import get_ocular_audio_video_context
    
    start = time.perf_counter()
    result = await get_ocular_audio_video_context(
        SHORT_VIDEO, 
        detail_level="auto",
        use_local_whisper=False
    )
    elapsed = time.perf_counter() - start
    
    screenshots = sum(1 for item in result if hasattr(item, 'path'))
    return elapsed, screenshots

async def benchmark_concurrent():
    """Benchmark concurrent requests."""
    from ocular_audio_mcp import get_ocular_audio_transcript
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "https://www.youtube.com/watch?v=JGwWNGJdvx8",
    ]
    
    start = time.perf_counter()
    tasks = [get_ocular_audio_transcript(url, use_local_whisper=False) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - start
    
    success = sum(1 for r in results if not isinstance(r, Exception))
    return elapsed, success, len(urls)

async def benchmark_cache_sizes():
    """Measure cache file sizes."""
    from pathlib import Path
    
    cache_dir = Path.home() / ".cache" / "ocular_audio_mcp"
    if not cache_dir.exists():
        return {}
    
    sizes = {}
    for f in cache_dir.glob("*.json"):
        size_kb = f.stat().st_size / 1024
        sizes[f.stem] = round(size_kb, 1)
    
    return sizes

async def benchmark_detailed_cache():
    """Benchmark cache hit vs miss in detail."""
    from ocular_audio_mcp import get_ocular_audio_transcript
    
    # First call - should be cache hit if exists
    start = time.perf_counter()
    result1 = await get_ocular_audio_transcript(SHORT_VIDEO, use_local_whisper=False)
    time1 = time.perf_counter() - start
    is_cached1 = "[CACHE HIT" in result1
    
    # Second call - definitely cache hit
    start = time.perf_counter()
    result2 = await get_ocular_audio_transcript(SHORT_VIDEO, use_local_whisper=False)
    time2 = time.perf_counter() - start
    is_cached2 = "[CACHE HIT" in result2
    
    return {
        "first_call_time": time1,
        "first_call_cached": is_cached1,
        "second_call_time": time2,
        "second_call_cached": is_cached2,
        "speedup": time1 / time2 if time2 > 0 else float('inf')
    }

async def main():
    print("=" * 70)
    print("OCULARAUDIO MCP — EXTENDED PERFORMANCE BENCHMARKS")
    print("=" * 70)
    
    # System info
    import psutil
    ram = psutil.virtual_memory()
    print(f"\nTest Environment:")
    print(f"  OS: Windows 11")
    print(f"  CPU: AMD Ryzen (Family 23, Model 113)")
    print(f"  RAM: {ram.total / (1024**3):.1f} GB ({ram.available / (1024**3):.1f} GB available)")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  OpenCV: 5.0.0")
    print(f"  Faster-Whisper: tiny model")
    print(f"  FFmpeg: 8.1.1")
    print(f"  Tesseract: 5.x")
    
    results = {}
    
    # 1. Cache hit/miss comparison
    print("\n[1/6] Cache hit vs miss comparison...")
    try:
        cache_result = await benchmark_detailed_cache()
        results["Cache (first call)"] = (cache_result["first_call_time"], f"Cached: {cache_result['first_call_cached']}")
        results["Cache (second call)"] = (cache_result["second_call_time"], f"Cached: {cache_result['second_call_cached']}, Speedup: {cache_result['speedup']:.1f}x")
        print(f"  First call: {cache_result['first_call_time']:.4f}s (cached: {cache_result['first_call_cached']})")
        print(f"  Second call: {cache_result['second_call_time']:.4f}s (cached: {cache_result['second_call_cached']})")
        print(f"  Speedup: {cache_result['speedup']:.1f}x")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 2. Multiple screenshots
    print("\n[2/6] Multiple screenshots (5 frames)...")
    try:
        elapsed, success, total = await benchmark_multiple_screenshots()
        results["5 Screenshots"] = (elapsed, f"{success}/{total} captured")
        print(f"  Time: {elapsed:.2f}s ({success}/{total} frames)")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 3. Context auto mode
    print("\n[3/6] Full context (auto mode)...")
    try:
        elapsed, screenshots = await benchmark_context_auto()
        results["Context (auto)"] = (elapsed, f"{screenshots} screenshots")
        print(f"  Time: {elapsed:.2f}s ({screenshots} screenshots)")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 4. Concurrent requests
    print("\n[4/6] Concurrent requests (3 videos)...")
    try:
        elapsed, success, total = await benchmark_concurrent()
        results["3 Concurrent"] = (elapsed, f"{success}/{total} succeeded")
        print(f"  Time: {elapsed:.2f}s ({success}/{total} succeeded)")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 5. Cache sizes
    print("\n[5/6] Cache file sizes...")
    try:
        sizes = await benchmark_cache_sizes()
        if sizes:
            for vid_id, size in list(sizes.items())[:5]:
                print(f"  {vid_id}: {size} KB")
            total_kb = sum(sizes.values())
            results["Cache total"] = (0, f"{total_kb:.1f} KB ({len(sizes)} files)")
        else:
            print("  No cached files")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 6. Whisper benchmark (optional - takes time)
    print("\n[6/6] Whisper transcription (3:33 video)...")
    print("  (This downloads audio and transcribes locally - may take a while)")
    try:
        elapsed, result = await benchmark_whisper()
        if isinstance(result, int):
            results["Whisper (tiny)"] = (elapsed, f"{result} chars")
        else:
            results["Whisper (tiny)"] = (elapsed, str(result))
        print(f"  Time: {elapsed:.2f}s")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Print results table
    print("\n" + "=" * 70)
    print("EXTENDED BENCHMARK RESULTS")
    print("=" * 70)
    print(f"{'Task':<25} {'Time':<12} {'Notes'}")
    print("-" * 70)
    for task, (elapsed, notes) in results.items():
        print(f"{task:<25} {elapsed:<12.4f} {notes}")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
