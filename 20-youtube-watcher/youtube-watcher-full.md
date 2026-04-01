# YouTube Watcher - Complete Reference Guide

## What This Skill Does

The YouTube Watcher skill provides a simple way to fetch transcripts from YouTube videos. It uses a Python script called `get_transcript.py` that works with `yt-dlp` to download subtitles and convert them to clean, readable text.

Unlike the Summarize YouTube skill (Skill 16), this skill does not use artificial intelligence. It simply extracts the raw text from video captions. This makes it faster and completely free to use. You get exactly what was said in the video, word for word.

This skill is perfect for:
1. Creating written records of video content
2. Searching for specific quotes or statements
3. Translating video content to other formats
4. Building your own summaries without AI assistance
5. Archiving educational content for offline reading

## How It Works

The YouTube Watcher tool performs these steps:

**Step 1: Download Subtitles**
The tool uses `yt-dlp` to fetch subtitle files from YouTube. It looks for both manually created closed captions and auto-generated subtitles.

**Step 2: Clean the Text**
Subtitle files contain timestamps, HTML tags, and formatting codes. The tool removes all of this. You get plain text that is easy to read.

**Step 3: Remove Duplicates**
YouTube subtitles often repeat lines. The tool detects and removes duplicate text. This creates a natural reading flow.

**Step 4: Output Clean Transcript**
The final output is plain text you can copy, save, or process further.

## Understanding Subtitle Types

YouTube videos can have different types of subtitles. It is important to understand the difference:

### Manual Closed Captions (CC)

These are created by the video owner or professional captioners. They are highly accurate. They include speaker labels and sound descriptions. Look for the "CC" button on YouTube videos.

**Advantages:**
- Very accurate spelling and grammar
- Proper names are usually correct
- Includes non-speech information

**Disadvantages:**
- Not all videos have them
- Takes time to create, so new videos may not have them yet

### Auto-Generated Captions

YouTube automatically creates these using speech recognition. They appear as "English (auto-generated)" in the subtitle menu.

**Advantages:**
- Available on most videos
- Created automatically within hours of upload
- Supports many languages

**Disadvantages:**
- Less accurate than manual captions
- May struggle with accents or technical terms
- Speaker names are not labeled

### No Subtitles

Some videos have no captions at all. This tool cannot extract transcripts from these videos. The script will report an error.

## Dependencies and Installation

### Required Software

You need two things installed on your computer:

1. **Python 3** - Comes pre-installed on most Mac computers
2. **yt-dlp** - A command-line tool for downloading YouTube content

### Checking Python Installation

Open Terminal and type:

```bash
python3 --version
```

**What to expect:**
- If you see a version number like "Python 3.9.0", Python is installed
- If you see "command not found," you need to install Python

**To install Python:**
```bash
brew install python
```

### Installing yt-dlp

You have two options for installing yt-dlp. Choose the one that works best for you.

**Option 1: Install with Homebrew (Recommended)**

Homebrew is a package manager for Mac. If you do not have Homebrew installed, visit https://brew.sh for installation instructions.

Once Homebrew is ready, type:

```bash
brew install yt-dlp
```

**What to expect:**
- Installation takes about 30 seconds
- The tool is automatically added to your system path

**Option 2: Install with Python pip**

If you prefer using Python's package manager, type:

```bash
pip3 install yt-dlp
```

**What to expect:**
- Installation takes about 1 minute
- You may need to use `pip` instead of `pip3` on some systems

### Verifying yt-dlp Installation

After installation, test that yt-dlp works:

```bash
yt-dlp --version
```

You should see a version number like "2024.03.10". If you see an error, the installation failed.

## Usage Instructions

### Basic Command Structure

The script follows this pattern:

```bash
python3 {baseDir}/scripts/get_transcript.py "YOUTUBE_URL"
```

Replace `{baseDir}` with the actual path to the skill folder. Replace `YOUTUBE_URL` with the full YouTube video URL.

### Real-World Example

Here is how you actually run it:

```bash
python3 ~/.openclaw/skills/20-youtube-watcher/scripts/get_transcript.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**What to expect:**
1. The script downloads the subtitle file
2. It processes and cleans the text
3. The transcript appears in your terminal window
4. If no subtitles exist, you see an error message

### Saving Output to a File

To save the transcript instead of displaying it, use the `>` operator:

```bash
python3 ~/scripts/get_transcript.py "https://youtu.be/VIDEO_ID" > my_transcript.txt
```

This creates a file named `my_transcript.txt` containing the transcript.

### Viewing the File

After saving, you can:

**Open in TextEdit:**
```bash
open -a TextEdit my_transcript.txt
```

**Print to terminal:**
```bash
cat my_transcript.txt
```

**Count the words:**
```bash
wc -w my_transcript.txt
```

## Handling Multiple Languages

The script defaults to English subtitles. However, YouTube videos often have subtitles in multiple languages.

### How Language Selection Works

The script uses this priority order:

1. Manual captions in English
2. Auto-generated captions in English
3. If neither exists, the script reports "No subtitles found"

### Modifying the Script for Other Languages

To extract subtitles in a different language, you need to edit the script. Look for this line:

```python
"--sub-lang", "en",
```

Change `"en"` to your desired language code:

| Language | Code |
|----------|------|
| English | en |
| Spanish | es |
| French | fr |
| German | de |
| Portuguese | pt |
| Italian | it |
| Japanese | ja |
| Korean | ko |
| Chinese | zh |
| Russian | ru |

**Example for Spanish:**
```python
"--sub-lang", "es",
```

Save the file and run the script again.

## Error Handling and Troubleshooting

### Error: "No subtitles found"

**What it means:**
The video has no captions available in your requested language.

**Solutions:**

1. Check if the video has captions on YouTube:
   - Open the video in your browser
   - Click the CC button
   - See if any language options appear

2. Try a different language code (see section above)

3. Try a different video. Not all creators enable captions.

### Error: "yt-dlp not found"

**What it means:**
The yt-dlp tool is not installed or not in your system path.

**Solutions:**

1. Reinstall yt-dlp using Homebrew:
   ```bash
   brew reinstall yt-dlp
   ```

2. Check your system path:
   ```bash
   which yt-dlp
   ```
   If nothing appears, the tool is not in your path.

3. Try the full path to yt-dlp:
   ```bash
   /usr/local/bin/yt-dlp --version
   ```

### Error: "Video unavailable"

**What it means:**
The video cannot be accessed. This usually happens for these reasons:

1. The video was deleted or set to private
2. The video is region-restricted
3. The video URL is incorrect

**Solutions:**

1. Double-check the URL by opening it in your browser
2. Try a different video to confirm the script works
3. Some videos block automated downloads

### Error: "Age-restricted content"

**What it means:**
The video requires you to sign in to YouTube to confirm your age.

**Solutions:**

Unfortunately, this script cannot bypass age restrictions. You have these options:

1. Use a different video that is not age-restricted
2. Use yt-dlp with cookies from a logged-in session (advanced)
3. Try the Summarize YouTube skill instead, which may handle this differently

### Error: Python script fails with traceback

**What it means:**
Something unexpected went wrong in the code.

**Solutions:**

1. Make sure you are using Python 3:
   ```bash
   python3 --version
   ```

2. Check that the script file exists:
   ```bash
   ls -la ~/scripts/get_transcript.py
   ```

3. Try running with explicit Python path:
   ```bash
   /usr/bin/python3 ~/scripts/get_transcript.py "URL"
   ```

## Practical Examples

### Example 1: Get a Transcript for Note-Taking

**Scenario:** You watched an educational video and want to review the key points later.

**Command:**
```bash
python3 ~/scripts/get_transcript.py "https://youtu.be/LEARNING123" > notes.txt
```

**Result:** You have a text file you can search, highlight, and annotate.

### Example 2: Pipe to Summarize Tool

**Scenario:** You want both the raw transcript and an AI summary.

**Step 1 - Get transcript:**
```bash
python3 ~/scripts/get_transcript.py "https://youtu.be/VIDEO_ID" > transcript.txt
```

**Step 2 - Read and summarize:**
```bash
cat transcript.txt | summarize --length medium
```

Or use the Summarize YouTube skill directly for a one-step process.

### Example 3: Answer Questions About Video Content

**Scenario:** You need to find specific information in a long video.

**Step 1 - Get transcript:**
```bash
python3 ~/scripts/get_transcript.py "https://youtu.be/INTERVIEW456" > interview.txt
```

**Step 2 - Search for keywords:**
```bash
grep -i "pricing" interview.txt
```

The `-i` flag makes the search case-insensitive.

### Example 4: Process Multiple Videos

**Scenario:** You have a playlist of videos to transcribe.

Create a script called `batch_transcribe.sh`:

```bash
#!/bin/bash

videos=(
  "https://youtu.be/video1"
  "https://youtu.be/video2"
  "https://youtu.be/video3"
)

for url in "${videos[@]}"; do
  # Extract video ID from URL
  video_id=$(echo "$url" | grep -oE '[?&]v=([^&]+)' | cut -d= -f2)
  
  echo "Processing: $video_id"
  python3 ~/scripts/get_transcript.py "$url" > "transcript_${video_id}.txt"
done

echo "All videos processed!"
```

Run the script:
```bash
bash batch_transcribe.sh
```

## Difference Between This Skill and Skill 16

These two skills serve similar but distinct purposes. Here is how to choose:

### Use YouTube Watcher (This Skill, Skill 20) When:

- You want the exact, word-for-word transcript
- You do not want to use AI or API keys
- You need to search or process the text yourself
- You want to save money (no API costs)
- You need the fastest possible result
- You want to verify AI summaries against the source

### Use Summarize YouTube (Skill 16) When:

- You want a condensed summary, not full text
- You prefer AI-generated key points
- You do not need exact quotes
- You want the tool to interpret and organize information
- You are comfortable using API keys

### Quick Comparison Table

| Feature | YouTube Watcher (Skill 20) | Summarize YouTube (Skill 16) |
|---------|---------------------------|------------------------------|
| Output | Raw transcript | AI summary |
| Requires API keys | No | Yes (OpenAI or Gemini) |
| Cost | Free | Pay per use (API costs) |
| Speed | Fast | Slower (API call needed) |
| Accuracy | Exact words | Interpreted content |
| Best for | Research, quotes | Quick understanding |

## Working with Transcript Output

### Understanding the Output Format

The script produces plain text with these characteristics:

- No timestamps (removed during cleaning)
- No HTML tags
- No duplicate lines
- Paragraph breaks preserved
- Natural reading flow

### Example Output

**YouTube subtitles (raw):**
```
WEBVTT

00:00:00.000 --> 00:00:03.000
Welcome to the tutorial

00:00:03.000 --> 00:00:06.000
Welcome to the tutorial

00:00:06.000 --> 00:00:10.000
Today we will learn about Python
```

**Cleaned output:**
```
Welcome to the tutorial
Today we will learn about Python
```

Notice how timestamps and duplicate lines are removed.

### Processing the Transcript Further

Once you have the transcript, you can:

**Convert to PDF:**
```bash
cat transcript.txt | textutil -convert pdf -stdin -output transcript.pdf
```

**Count lines, words, characters:**
```bash
wc transcript.txt
```

**Extract unique words:**
```bash
tr ' ' '\n' < transcript.txt | sort | uniq > unique_words.txt
```

## Best Practices

**1. Always Verify Captions Exist First**
Before running the script, check the YouTube video. Make sure it has captions in your desired language.

**2. Save to Files for Long Videos**
Long videos produce lots of text. Always redirect output to a file instead of displaying in terminal.

**3. Handle Errors Gracefully**
Not all videos work. Build error handling into your scripts. Expect some videos to fail.

**4. Respect Copyright**
Transcripts are for personal use. Do not redistribute copyrighted content without permission.

**5. Cross-Check Important Quotes**
Auto-generated captions can have errors. For critical quotes, listen to the audio to verify accuracy.

## Integration with OpenClaw

OpenClaw agents can use this skill directly. When you ask for a transcript, here is what happens:

**You say:** "Get me the transcript from this video"

**Agent does:**
1. Identifies the YouTube URL in your message
2. Runs the get_transcript.py script
3. Returns the clean text to you

**You say:** "Search this video for mentions of pricing"

**Agent does:**
1. Fetches the transcript using this skill
2. Searches for the word "pricing"
3. Shows you the relevant sections

### When the Agent Chooses This Skill vs Skill 16

The agent makes intelligent choices based on your request:

- **"Transcript" or "exact words"** -> Uses YouTube Watcher (Skill 20)
- **"Summary" or "what does it say"** -> Uses Summarize YouTube (Skill 16)
- **"Find quotes" or "search video"** -> Uses YouTube Watcher (Skill 20)

## Advanced Configuration

### Customizing the Script

The script can be modified for special use cases. Open `get_transcript.py` in a text editor.

**Keep timestamps (modify cleaning function):**
If you want to keep timestamps for reference, comment out the timestamp removal:

```python
# if timestamp_pattern.match(line):
#     continue
```

**Change output encoding:**
For special characters, modify the encoding:

```python
content = vtt_file.read_text(encoding='utf-8-sig')
```

### Using yt-dlp Options

The script uses these yt-dlp options:

- `--write-subs` - Download manual subtitles
- `--write-auto-subs` - Download auto-generated subtitles
- `--skip-download` - Do not download the video file
- `--sub-lang en` - English language only
- `--output subs` - Name the output file

You can modify these in the script for different behavior.

## Conclusion

The YouTube Watcher skill provides a simple, free way to extract text from YouTube videos. By understanding how subtitles work, installing the right dependencies, and using the script correctly, you can turn any captioned video into readable text.

Remember the key points:
- This skill extracts raw transcripts without AI
- You need Python 3 and yt-dlp installed
- Not all videos have subtitles
- Use Skill 16 if you want AI summaries instead

With this skill, you can efficiently process video content, search for information, and build your own knowledge base from YouTube's vast library of educational content.
