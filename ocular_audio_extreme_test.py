import os
import sys
import asyncio
import time
from pathlib import Path
from ocular_audio_mcp import (
    extract_video_id,
    get_ocular_audio_transcript,
    get_ocular_audio_video_screenshots,
    CACHE_DIR
)

# Color constants for high-fidelity professional reporting
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

async def test_regex_weird_characters():
    print(f"{BOLD}[EDGE CASE 1: Weird ID Characters]{RESET} Testing ID extraction for characters like dashes and underscores...")
    url = "https://www.youtube.com/watch?v=aA3O-mczM_8"
    video_id = extract_video_id(url)
    
    if video_id == "aA3O-mczM_8":
        print(f"  {GREEN}[PASSED]{RESET} Extracted complex video ID '{video_id}' successfully.")
        return True
    else:
        print(f"  {RED}[FAILED]{RESET} FAILED extraction for complex ID: Got '{video_id}'")
        return False


async def test_general_web_video():
    print(f"\n{BOLD}[EDGE CASE 2: Multi-Platform Generalization]{RESET} Testing General Web Video support (Vimeo)...")
    vimeo_url = "https://vimeo.com/76979871"
    
    start_time = time.time()
    try:
        print("  Querying Vimeo metadata asynchronously...")
        result = await get_ocular_audio_transcript(vimeo_url, use_local_whisper=False)
        duration = time.time() - start_time
        
        print(f"  Completed in {duration:.2f} seconds.")
        if "Vimeo" in result or "Web Video" in result:
            print(f"  {GREEN}[PASSED]{RESET} Successfully parsed non-YouTube platform metadata (Uploader, Title, etc.)!")
            print(f"  Result heading was:\n{result[:150]}...")
            return True
        else:
            print(f"  {RED}[FAILED]{RESET} Failed to fetch metadata for general web video: {result[:200]}")
            return False
    except Exception as e:
        print(f"  {RED}[ERROR]{RESET} Error occurred: {e}")
        return False


async def test_out_of_bounds_screenshots():
    print(f"\n{BOLD}[EDGE CASE 3: Frame Bound Protections]{RESET} Requesting screenshots beyond video duration...")
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    start_time = time.time()
    visual_results = await get_ocular_audio_video_screenshots(test_url, timestamps_secs=[99999])
    duration = time.time() - start_time
    
    print(f"  Bound check completed in {duration:.2f} seconds.")
    if len(visual_results) >= 2:
        warning_msg = visual_results[1]
        if "beyond the end of the video" in warning_msg:
            print(f"  {GREEN}[PASSED]{RESET} Output matched expected bound protection: '{warning_msg}'")
            return True
    print(f"  {RED}[FAILED]{RESET} FAILED to intercept out-of-bounds screenshot request safely.")
    return False


async def test_invalid_arbitrary_url():
    print(f"\n{BOLD}[EDGE CASE 4: Defending Against Arbitrary Web URLs]{RESET} Feeding standard non-video web pages...")
    gibberish_url = "https://example.com/not_a_video"
    
    start_time = time.time()
    result = await get_ocular_audio_transcript(gibberish_url, use_local_whisper=False)
    duration = time.time() - start_time
    
    print(f"  Completed in {duration:.2f} seconds.")
    if "Error:" in result or "Failed" in result or "disabled" in result:
        print(f"  {GREEN}[PASSED]{RESET} System securely trapped the error without raising an unhandled exception.")
        print(f"  Returned String: {result[:120]}...")
        return True
    else:
        print(f"  {RED}[FAILED]{RESET} Unexpected return string for invalid page: {result}")
        return False


async def execute_extreme_testing_suite():
    print(f"{BOLD}{CYAN}==================================================")
    print("RUNNING OCULARAUDIO MCP EXTREME ROBUSTNESS SUITE")
    print("=================================================={RESET}\n")
    
    t1 = await test_regex_weird_characters()
    t2 = await test_general_web_video()
    t3 = await test_out_of_bounds_screenshots()
    t4 = await test_invalid_arbitrary_url()
    
    print(f"\n{BOLD}{CYAN}==================================================")
    print("OCULARAUDIO EXTREME TESTING DASHBOARD")
    print(f"=================================================={RESET}")
    print(f"1. Weird ID Regex Validation:     {GREEN if t1 else RED}{'PASSED' if t1 else 'FAILED'}{RESET}")
    print(f"2. Multi-Platform Generalization: {GREEN if t2 else RED}{'PASSED' if t2 else 'FAILED'}{RESET}")
    print(f"3. Screenshot Boundary Protection: {GREEN if t3 else RED}{'PASSED' if t3 else 'FAILED'}{RESET}")
    print(f"4. Non-Video Page Protection:     {GREEN if t4 else RED}{'PASSED' if t4 else 'FAILED'}{RESET}")
    print(f"{BOLD}{CYAN}=================================================={RESET}\n")
    
    if t1 and t2 and t3 and t4:
        print(f"{BOLD}{GREEN}ALL EXTREME EDGE CASES PASSED! THE OCULARAUDIO ENGINE IS INDESTRUCTIBLE.{RESET}")
    else:
        print(f"{BOLD}{RED}SOME EDGE CASES FAILED. AUDIT RESILIENCE BLOCKS.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(execute_extreme_testing_suite())
