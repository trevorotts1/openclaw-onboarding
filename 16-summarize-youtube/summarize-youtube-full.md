# Summarize YouTube - Complete Reference Guide

## What This Skill Does

The Summarize YouTube skill installs and configures the `summarize` command-line tool. This tool extracts transcripts from YouTube videos, podcasts, and web pages. It then generates clean, readable summaries using artificial intelligence.

Think of it as a research assistant that watches videos for you. Instead of spending 30 minutes watching a video, you get the key points in under a minute. This skill is essential when you need to:

1. Understand video content without watching the entire thing
2. Extract transcripts for note-taking or documentation
3. Summarize podcast episodes quickly
4. Create briefs from webinar recordings
5. Research topics covered in video format

## How the Summarize Tool Works

The summarize tool performs two main tasks:

**Task 1: Extract Transcripts**
The tool downloads the spoken words from videos. It uses a program called `yt-dlp` to fetch subtitles. These can be official closed captions added by the video creator. They can also be auto-generated subtitles created by YouTube's speech recognition system.

**Task 2: Generate Summaries**
After extracting the transcript, the tool sends the text to an AI service. The AI reads through all the content. It then produces a condensed version that captures the main ideas. You can choose summary length: short, medium, or long.

## Installation Instructions

### Step 1: Check if Homebrew is Installed

Homebrew is a package manager for Mac computers. It helps install command-line tools. Open your Terminal application. Type this command and press Enter:

```bash
brew --version
```

**What to expect:**
- If you see a version number (like "Homebrew 4.x"), Homebrew is installed. Skip to Step 2.
- If you see "command not found," you need to install Homebrew first.

**To install Homebrew:**
Copy and paste this entire command into Terminal. Press Enter:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

The installation will take several minutes. You may need to enter your computer password. Just follow the on-screen prompts.

### Step 2: Install the Summarize Tool

Once Homebrew is ready, install the summarize tool with this command:

```bash
brew install steipete/tap/summarize
```

This command does several things:
1. Adds the software repository (tap) from developer Steipete
2. Downloads the summarize program
3. Installs it on your system
4. Makes it available in your command line

**What to expect:**
- You will see download progress messages
- Installation completes in about 30-60 seconds
- No confirmation message appears when done

### Step 3: Verify the Installation

Type this command to confirm the tool installed correctly:

```bash
summarize --help
```

**What to expect:**
- You should see a help message listing all available options
- If you see "command not found," the installation failed. Try running the install command again.

## Required API Keys

The summarize tool needs access to artificial intelligence services. It requires API keys from either OpenAI or Google Gemini. These keys act like passwords that let the tool use AI models.

### Getting Your OpenAI API Key

1. Open your web browser and go to: https://platform.openai.com
2. Click "Sign Up" if you do not have an account, or "Log In" if you do
3. Once logged in, click on your profile name (top right corner)
4. Select "API Keys" from the dropdown menu
5. Click the "Create new secret key" button
6. Give your key a name (like "Summarize Tool")
7. Click "Create"
8. **Important:** Copy the key immediately. It looks like "sk-" followed by random letters and numbers
9. Store this key in a safe place. You cannot see it again after closing this window

### Getting Your Google Gemini API Key

1. Open your web browser and go to: https://aistudio.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Select "Generative Language API" from the dropdown
5. Click "Create"
6. Copy the key that appears. It is a long string of letters and numbers
7. Store this key safely

### Setting Up Environment Variables

The summarize tool reads API keys from environment variables. These are special settings that programs can access. You need to create a file named `.env` in your working directory.

**Step 1: Create the .env file**

Open Terminal. Navigate to your project folder. Type:

```bash
touch .env
```

**Step 2: Add your API keys**

Open the .env file in a text editor. Add these lines:

```bash
OPENAI_API_KEY=your_openai_key_here
GEMINI_API_KEY=your_gemini_key_here
```

Replace "your_openai_key_here" with your actual OpenAI key. Replace "your_gemini_key_here" with your actual Gemini key.

**Step 3: Load the environment variables**

Each time you open a new Terminal window, load the variables with:

```bash
set -a
source .env
set +a
```

These commands:
- `set -a` tells the shell to export all variables
- `source .env` reads the file and sets the variables
- `set +a` returns to normal mode

## Command Line Options

The summarize tool accepts several options to control its behavior. Here is the complete list:

### --youtube Option

This flag tells the tool to process a YouTube video URL.

**Usage:**
```bash
summarize "https://youtu.be/VIDEO_ID" --youtube
```

The `--youtube` flag accepts a quality parameter. The "auto" setting lets the tool choose the best available subtitles.

**Full example:**
```bash
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto
```

### --length Option

This option controls how long or short the summary should be. You have three choices:

| Length | Description | Best For |
|--------|-------------|----------|
| short | 1-2 paragraphs | Quick overview, busy schedules |
| medium | 3-4 paragraphs | Balanced detail and brevity |
| long | Full page | Detailed analysis, research |

**Usage:**
```bash
summarize "URL" --youtube auto --length short
summarize "URL" --youtube auto --length medium
summarize "URL" --youtube auto --length long
```

**Recommendation:**
- Use "short" for videos under 5 minutes
- Use "medium" for videos 5-20 minutes
- Use "long" for videos over 20 minutes or complex topics

### --extract-only Option

This flag skips the AI summarization. It only extracts and prints the raw transcript. This is useful when:

1. You want to read the full transcript yourself
2. You plan to use the text in another program
3. You need to search for specific words or phrases
4. You want to save the transcript to a file

**Usage:**
```bash
summarize "https://youtu.be/VIDEO_ID" --youtube auto --extract-only
```

**Save transcript to file:**
```bash
summarize "https://youtu.be/VIDEO_ID" --youtube auto --extract-only > transcript.txt
```

The `>` symbol redirects the output to a file instead of displaying it on screen.

### --format Option

This option controls the output format. The summarize tool supports multiple formats for different use cases.

**Available formats:**
- `text` (default) - Plain text output
- `markdown` - Formatted with headers and bullets
- `json` - Machine-readable JSON format

**Usage:**
```bash
summarize "URL" --youtube auto --length medium --format markdown
```

### --language Option

This option specifies the language for the transcript. The tool tries to auto-detect, but you can force a specific language.

**Common language codes:**
- `en` - English
- `es` - Spanish
- `fr` - French
- `de` - German
- `ja` - Japanese

**Usage:**
```bash
summarize "URL" --youtube auto --language en
```

## API Key Fallback Chain

The summarize tool has a smart fallback system. This ensures it keeps working even if one AI service has problems.

**How it works:**

1. **First attempt:** The tool tries OpenAI first. This is the preferred service.

2. **If OpenAI fails:** The tool automatically tries Gemini as a backup.

3. **If both fail:** The tool stops and shows the error message.

**Why this matters:**
- OpenAI might be down for maintenance
- Your OpenAI credits might run out
- Network issues might block one service but not the other
- Gemini might have different content policies

**Example execution with fallback:**
```bash
# Try OpenAI first, fallback to Gemini if needed
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short || summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short
```

The `||` symbol means "if the first command fails, run the second command."

## Practical Examples

### Example 1: Summarize a YouTube Video

**Scenario:** You need to understand a 45-minute tutorial but only have 5 minutes.

**Command:**
```bash
summarize "https://www.youtube.com/watch?v=EXAMPLE123" --youtube auto --length medium
```

**What happens:**
1. The tool downloads the video's subtitles
2. It sends the transcript to OpenAI
3. OpenAI generates a 3-4 paragraph summary
4. You read the summary and understand the key points

### Example 2: Extract Transcript Only

**Scenario:** You want to quote exact words from a speech.

**Command:**
```bash
summarize "https://youtu.be/SPEECH456" --youtube auto --extract-only > speech.txt
```

**What happens:**
1. The tool downloads the subtitles
2. It cleans and formats the text
3. It saves the transcript to a file named speech.txt
4. You can now search the file for specific quotes

### Example 3: Summarize a Podcast URL

**Scenario:** You want to catch up on a podcast episode during your commute.

**Command:**
```bash
summarize "https://example.com/podcast/episode-42" --length short
```

**Note:** For podcasts not on YouTube, the tool uses web scraping to find any available transcript.

### Example 4: Summarize a Web Page

**Scenario:** You need to quickly understand a long article.

**Command:**
```bash
summarize "https://example.com/long-article" --length medium
```

The tool fetches the web page, extracts the main text, and summarizes it.

## Troubleshooting Common Problems

### Problem: "Missing OPENAI_API_KEY or GEMINI_API_KEY"

**Symptoms:**
You see an error saying API keys are missing.

**Solutions:**

1. Check that your .env file exists:
   ```bash
   ls -la .env
   ```

2. Verify the keys are in the file:
   ```bash
   cat .env
   ```
   
3. Make sure you loaded the environment variables:
   ```bash
   set -a && source .env && set +a
   ```

4. Test that the variables are set:
   ```bash
   echo $OPENAI_API_KEY
   ```
   This should show your key (partially hidden).

### Problem: "brew: command not found"

**Symptoms:**
Terminal says it cannot find the brew command.

**Solution:**
Homebrew is not installed. Follow the installation instructions in Step 1 of the Installation section. You must install Homebrew before you can install the summarize tool.

### Problem: "yt-dlp not found"

**Symptoms:**
The tool complains that yt-dlp is missing or not installed.

**Solutions:**

1. Install yt-dlp using Homebrew:
   ```bash
   brew install yt-dlp
   ```

2. Or install using Python pip:
   ```bash
   pip3 install yt-dlp
   ```

3. Verify installation:
   ```bash
   yt-dlp --version
   ```

### Problem: "No subtitles found"

**Symptoms:**
The tool cannot find any transcript for the video.

**Reasons:**
1. The video has no subtitles at all
2. The video has subtitles but not in English
3. The video creator disabled auto-generated captions
4. The video is too new and captions have not been generated yet

**Solutions:**

1. Try specifying a different language:
   ```bash
   summarize "URL" --youtube auto --language es
   ```

2. Check if the video actually has captions on YouTube
3. Try a different video that has captions enabled

### Problem: "API rate limit exceeded"

**Symptoms:**
You see an error about rate limits from OpenAI or Gemini.

**Solution:**
Wait a few minutes and try again. Free tiers have strict limits. Consider upgrading to a paid plan for higher limits.

### Problem: Summary is empty or gibberish

**Symptoms:**
The tool runs but produces nonsense output.

**Reasons:**
1. The video has poor audio quality
2. The auto-generated captions are very inaccurate
3. The API key is invalid

**Solutions:**

1. Try a different video with better audio
2. Check that your API key is valid
3. Try switching to the other AI service (Gemini instead of OpenAI, or vice versa)

## Integration with OpenClaw

OpenClaw uses this skill through its agent system. When you ask an OpenClaw agent to summarize a YouTube video, here is what happens behind the scenes:

**Step 1: Trigger Detection**
The agent recognizes phrases like:
- "Summarize this video"
- "Get the transcript from YouTube"
- "What does this video say?"

**Step 2: Tool Execution**
The agent runs the summarize command with appropriate options. It automatically:
- Loads API keys from the environment
- Tries OpenAI first
- Falls back to Gemini if needed
- Returns the results to you

**Step 3: Error Handling**
If something goes wrong, the agent:
- Reports the exact error message
- Suggests troubleshooting steps
- Never exposes your API keys in messages

**Example agent interaction:**

**You say:** "Please summarize this video: https://youtu.be/example123"

**Agent does:**
1. Runs: `summarize "https://youtu.be/example123" --youtube auto --length medium`
2. Receives the summary from the AI
3. Presents it to you in a readable format

**You say:** "Get me the full transcript"

**Agent does:**
1. Runs: `summarize "https://youtu.be/example123" --youtube auto --extract-only`
2. Formats the transcript for display
3. Optionally saves it to a file if you request

## Best Practices

**1. Always Use Extract-Only for Long Content**
If you need the full text, use `--extract-only`. The AI summary is great for quick understanding but may miss details you care about.

**2. Choose the Right Length**
Short summaries work well for simple topics. Use long summaries for technical content or when you need comprehensive coverage.

**3. Keep Your API Keys Safe**
Never share your .env file. Never paste API keys into chat messages. Treat them like passwords.

**4. Check Video Length**
Very long videos (over 2 hours) may hit token limits. Consider using `--extract-only` and summarizing sections yourself.

**5. Verify Accuracy**
AI summaries capture main ideas but can miss nuance. For critical information, always check the original transcript using `--extract-only`.

## Advanced Usage Tips

### Piping Output to Other Commands

You can chain summarize with other command-line tools:

**Count words in transcript:**
```bash
summarize "URL" --youtube auto --extract-only | wc -w
```

**Search transcript for keyword:**
```bash
summarize "URL" --youtube auto --extract-only | grep "keyword"
```

**Send summary to clipboard (Mac):**
```bash
summarize "URL" --youtube auto --length short | pbcopy
```

### Processing Multiple Videos

Create a script to summarize several videos:

```bash
#!/bin/bash
videos=(
  "https://youtu.be/video1"
  "https://youtu.be/video2"
  "https://youtu.be/video3"
)

for url in "${videos[@]}"; do
  echo "=== Summary for $url ==="
  summarize "$url" --youtube auto --length short
  echo ""
done
```

Save this as `summarize-all.sh` and run with `bash summarize-all.sh`.

## Conclusion

The Summarize YouTube skill transforms how you consume video content. Instead of spending hours watching, you get the key information in minutes. With automatic fallback between OpenAI and Gemini, reliable error handling, and flexible output options, this tool belongs in every knowledge worker's toolkit.

Remember the key commands:
- `summarize "URL" --youtube auto --length medium` for standard summaries
- `summarize "URL" --youtube auto --extract-only` for full transcripts
- Always keep your API keys in .env and load them before use

With this skill installed, you can efficiently process video content at scale. Whether you are researching, learning, or just staying informed, the summarize tool saves you time while delivering the information you need.
