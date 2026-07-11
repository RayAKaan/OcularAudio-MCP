import time
import sys
import asyncio

# Test URLs
SHORT_VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - 3:33
LONG_VIDEO = "https://www.youtube.com/watch?v=aircAruvnKk"  # 3Blue1Brown - Neural Networks - 19:47

async def benchmark_metadata():
    from ocular_audio_mcp import _blocking_metadata_fetch, find_cookies_file
    cookies = find_cookies_file()
    
    start = time.perf_counter()
    meta = await asyncio.to_thread(_blocking_metadata_fetch, SHORT_VIDEO, cookies)
    elapsed = time.perf_counter() - start
    return elapsed, meta.get("title", "Unknown")

async def benchmark_transcript_short():
    from ocular_audio_mcp import get_ocular_audio_transcript
    from youtube_transcript_api import YouTubeTranscriptApi
    
    start = time.perf_counter()
    result = await get_ocular_audio_transcript(SHORT_VIDEO, use_local_whisper=False)
    elapsed = time.perf_counter() - start
    return elapsed, len(result)

async def benchmark_transcript_long():
    from ocular_audio_mcp import get_ocular_audio_transcript
    
    start = time.perf_counter()
    result = await get_ocular_audio_transcript(LONG_VIDEO, use_local_whisper=False)
    elapsed = time.perf_counter() - start
    return elapsed, len(result)

async def benchmark_screenshot():
    from ocular_audio_mcp import get_ocular_audio_video_screenshots
    
    start = time.perf_counter()
    result = await get_ocular_audio_video_screenshots(SHORT_VIDEO, timestamps_secs=[30])
    elapsed = time.perf_counter() - start
    return elapsed, len(result)

async def benchmark_ocr():
    from ocular_audio_mcp import extract_text_from_frame, get_ocular_audio_video_screenshots
    
    # First capture a screenshot
    result = await get_ocular_audio_video_screenshots(SHORT_VIDEO, timestamps_secs=[30])
    # Find the image path
    img_path = None
    for item in result:
        if hasattr(item, 'path'):
            img_path = item.path
            break
    
    if img_path:
        start = time.perf_counter()
        text = extract_text_from_frame(img_path)
        elapsed = time.perf_counter() - start
        return elapsed, len(text)
    return 0, 0

async def benchmark_cache_hit():
    from ocular_audio_mcp import get_ocular_audio_transcript
    
    # Should be cached from previous call
    start = time.perf_counter()
    result = await get_ocular_audio_transcript(SHORT_VIDEO, use_local_whisper=False)
    elapsed = time.perf_counter() - start
    return elapsed, "[CACHE HIT" in result

async def main():
    print("Running OcularAudio MCP Performance Benchmarks...")
    print("=" * 60)
    
    # System info
    print("\nTest Environment:")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Platform: {sys.platform}")
    
    results = {}
    
    # Benchmark 1: Metadata
    print("\n[1/5] Metadata fetch...")
    try:
        elapsed, title = await benchmark_metadata()
        results["Metadata"] = (elapsed, f"Title: {title[:40]}...")
        print(f"  Done: {elapsed:.2f}s")
    except Exception as e:
        print(f"  Error: {e}")
        results["Metadata"] = (0, f"Error: {e}")
    
    # Benchmark 2: Short transcript
    print("\n[2/5] Short transcript (3:33 video)...")
    try:
        elapsed, size = await benchmark_transcript_short()
        results["Transcript (3:33)"] = (elapsed, f"{size} chars")
        print(f"  Done: {elapsed:.2f}s")
    except Exception as e:
        print(f"  Error: {e}")
        results["Transcript (3:33)"] = (0, f"Error: {e}")
    
    # Benchmark 3: Long transcript
    print("\n[3/5] Long transcript (19:47 video)...")
    try:
        elapsed, size = await benchmark_transcript_long()
        results["Transcript (19:47)"] = (elapsed, f"{size} chars")
        print(f"  Done: {elapsed:.2f}s")
    except Exception as e:
        print(f"  Error: {e}")
        results["Transcript (19:47)"] = (0, f"Error: {e}")
    
    # Benchmark 4: Screenshot
    print("\n[4/5] Screenshot capture...")
    try:
        elapsed, count = await benchmark_screenshot()
        results["Screenshot @ 30s"] = (elapsed, f"{count} images")
        print(f"  Done: {elapsed:.2f}s")
    except Exception as e:
        print(f"  Error: {e}")
        results["Screenshot @ 30s"] = (0, f"Error: {e}")
    
    # Benchmark 5: Cache hit
    print("\n[5/5] Cache hit...")
    try:
        elapsed, cached = await benchmark_cache_hit()
        results["Cache hit"] = (elapsed, f"Cached: {cached}")
        print(f"  Done: {elapsed:.4f}s")
    except Exception as e:
        print(f"  Error: {e}")
        results["Cache hit"] = (0, f"Error: {e}")
    
    # Print results table
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"{'Task':<25} {'Time':<10} {'Notes'}")
    print("-" * 60)
    for task, (elapsed, notes) in results.items():
        print(f"{task:<25} {elapsed:<10.4f} {notes}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
