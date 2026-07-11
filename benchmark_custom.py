import time
import sys
import asyncio

VIDEOS = [
    ("Rtkac4WHC1o", "https://youtu.be/Rtkac4WHC1o"),
    ("LzMnsfqjzkA", "https://youtu.be/LzMnsfqjzkA"),
]

async def benchmark_video(video_id, url):
    from ocular_audio_mcp import (
        _blocking_metadata_fetch, 
        get_ocular_audio_transcript,
        get_ocular_audio_video_screenshots,
        find_cookies_file
    )
    
    cookies = find_cookies_file()
    results = {}
    
    # 1. Metadata
    start = time.perf_counter()
    try:
        meta = await asyncio.to_thread(_blocking_metadata_fetch, url, cookies)
        elapsed = time.perf_counter() - start
        results["Metadata"] = (elapsed, meta.get("title", "Unknown"), meta.get("duration", "Unknown"))
    except Exception as e:
        elapsed = time.perf_counter() - start
        results["Metadata"] = (elapsed, f"Error: {e}", "")
    
    # 2. Transcript (cache miss if not cached)
    start = time.perf_counter()
    try:
        result = await get_ocular_audio_transcript(url, use_local_whisper=False)
        elapsed = time.perf_counter() - start
        is_cached = "[CACHE HIT" in result
        results["Transcript"] = (elapsed, is_cached, len(result))
    except Exception as e:
        elapsed = time.perf_counter() - start
        results["Transcript"] = (elapsed, False, f"Error: {e}")
    
    # 3. Transcript (cache hit)
    start = time.perf_counter()
    try:
        result = await get_ocular_audio_transcript(url, use_local_whisper=False)
        elapsed = time.perf_counter() - start
        is_cached = "[CACHE HIT" in result
        results["Transcript (cached)"] = (elapsed, is_cached, len(result))
    except Exception as e:
        elapsed = time.perf_counter() - start
        results["Transcript (cached)"] = (elapsed, False, f"Error: {e}")
    
    # 4. Screenshot
    start = time.perf_counter()
    try:
        result = await get_ocular_audio_video_screenshots(url, timestamps_secs=[60])
        elapsed = time.perf_counter() - start
        success = sum(1 for item in result if hasattr(item, 'path'))
        results["Screenshot"] = (elapsed, success, "")
    except Exception as e:
        elapsed = time.perf_counter() - start
        results["Screenshot"] = (elapsed, 0, f"Error: {e}")
    
    return results

async def main():
    print("=" * 70)
    print("CUSTOM VIDEO BENCHMARKS")
    print("=" * 70)
    
    all_results = {}
    
    for video_id, url in VIDEOS:
        print(f"\n{'=' * 70}")
        print(f"Video: {video_id}")
        print(f"URL: {url}")
        print("=" * 70)
        
        results = await benchmark_video(video_id, url)
        all_results[video_id] = results
        
        for task, data in results.items():
            elapsed = data[0]
            notes = data[1:]
            print(f"  {task}: {elapsed:.4f}s — {notes}")
    
    # Summary table
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Video':<15} {'Task':<20} {'Time':<10} {'Notes'}")
    print("-" * 70)
    for video_id, results in all_results.items():
        for task, data in results.items():
            elapsed = data[0]
            notes = str(data[1:])
            print(f"{video_id:<15} {task:<20} {elapsed:<10.4f} {notes}")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
