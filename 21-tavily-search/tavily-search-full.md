# Tavily Search - Complete Reference Guide

## What Is Tavily?

Tavily is a search engine built specifically for artificial intelligence systems. Unlike regular search engines that give you a list of links, Tavily understands what AI needs. It returns clean, relevant content that AI can read and use immediately.

Think of Tavily as a research librarian for AI agents. When you ask a question, Tavily does not just find websites. It reads them, extracts the important parts, and presents organized information with source citations. This saves time and produces better results.

### Why Tavily Was Created

Traditional search engines were designed for humans clicking links. AI systems need something different. They need:

1. **Structured data** - Clean text, not HTML code
2. **Source citations** - Knowing where information came from
3. **Content extraction** - Reading pages without browsing
4. **AI-ready formatting** - Ready to process immediately

Tavily provides all of this. It is the search engine that AI systems prefer.

### Key Features

**AI-Optimized Results:**
Tavily processes search results before returning them. It removes ads, navigation menus, and clutter. You get pure content.

**Built-in Summaries:**
Many searches include an AI-generated answer at the top. This gives you the gist before you dive into sources.

**Relevance Scoring:**
Each result includes a relevance percentage. You know which sources are most trustworthy.

**Deep Search Mode:**
For complex research, Tavily can do advanced searching. This takes longer but finds more comprehensive information.

**Content Extraction:**
The extract feature pulls full article text from URLs. No need to visit websites manually.

## Getting Your API Key

Tavily requires an API key to use. The key is free to start. Here is how to get one:

### Step 1: Create an Account

1. Open your web browser
2. Go to https://tavily.com
3. Click the "Sign Up" button
4. Enter your email address and create a password
5. Verify your email address by clicking the link they send

### Step 2: Access Your API Key

1. Log in to your Tavily account
2. Click on "API Keys" in the dashboard
3. You will see your key displayed
4. Copy the key immediately

**Important:** Your API key is like a password. Keep it secret. Do not share it. Do not paste it into public documents.

### Step 3: Set the Environment Variable

Your API key must be stored in an environment variable. This keeps it secure while letting scripts use it.

**Create or edit your .env file:**

```bash
# Open Terminal
cd ~/your-project-folder
touch .env
```

**Add your API key:**

Open the .env file in a text editor. Add this line:

```bash
TAVILY_API_KEY=tvly-your-actual-key-here
```

Replace `tvly-your-actual-key-here` with your real key from Tavily.

**Load the environment variables:**

Every time you open a new Terminal window, run:

```bash
set -a
source .env
set +a
```

**Verify the key is set:**

```bash
echo $TAVILY_API_KEY
```

You should see your key (or part of it) displayed.

### Free Tier Limits

Tavily offers a generous free tier:

- **1,000 API calls per month**
- This includes both searches and extractions
- Resets monthly
- No credit card required

**Tracking usage:** Log in to your Tavily dashboard to see how many calls you have used.

**What happens when you hit the limit:** API calls will fail with an error until the next month or until you upgrade.

## The Two Scripts

This skill includes two Node.js scripts. Each serves a different purpose.

### Script 1: search.mjs

This script performs web searches. It queries Tavily's search engine and returns formatted results.

**Location:** `{baseDir}/scripts/search.mjs`

**What it does:**
1. Takes your search query
2. Sends it to Tavily's API
3. Receives structured results
4. Formats them for easy reading
5. Displays sources with relevance scores

### Script 2: extract.mjs

This script extracts full content from web pages. Give it a URL and it returns the article text.

**Location:** `{baseDir}/scripts/extract.mjs`

**What it does:**
1. Takes one or more URLs
2. Requests extracted content from Tavily
3. Receives clean article text
4. Handles failed URLs gracefully
5. Presents content in readable format

## Search Script Options

The search script accepts several command-line options. Here is the complete list:

### Basic Search

**Command:**
```bash
node {baseDir}/scripts/search.mjs "your search query"
```

**Example:**
```bash
node ~/tavily-search/scripts/search.mjs "latest AI developments 2024"
```

**Output includes:**
- AI-generated answer (if available)
- List of sources with titles
- URLs for each source
- Relevance scores as percentages
- Content snippets (first 300 characters)

### Option: -n (Number of Results)

Controls how many results to return.

**Default:** 5 results

**Maximum:** 20 results

**Minimum:** 1 result

**Usage:**
```bash
node scripts/search.mjs "query" -n 10
node scripts/search.mjs "query" -n 3
node scripts/search.mjs "query" -n 20
```

**When to use more results:**
- Comprehensive research projects
- Finding diverse viewpoints
- Academic citations

**When to use fewer results:**
- Quick fact-checking
- Limited time
- Simple queries with clear answers

### Option: --deep (Advanced Search)

Enables Tavily's deep search mode. This performs more thorough research.

**Default:** Basic search

**Trade-offs:**
- Takes 2-3x longer
- Finds more sources
- Better for complex topics
- Uses more API calls

**Usage:**
```bash
node scripts/search.mjs "quantum computing applications" --deep
```

**Best for:**
- Academic research
- Business intelligence
- Technical deep dives
- Competitive analysis

### Option: --topic (Search Topic)

Narrows the search to specific content types.

**Available topics:**
- `general` (default) - All web content
- `news` - News articles and recent publications

**Usage:**
```bash
node scripts/search.mjs "stock market" --topic news
```

**When to use news:**
- Current events
- Breaking stories
- Recent developments
- Time-sensitive information

### Option: --days (Time Filter)

Limits news searches to recent articles only.

**Works with:** Must be used with `--topic news`

**Usage:**
```bash
node scripts/search.mjs "tech announcements" --topic news --days 7
```

**Common values:**
- `--days 1` - Last 24 hours
- `--days 7` - Last week
- `--days 30` - Last month

**Example - Recent AI News:**
```bash
node scripts/search.mjs "artificial intelligence" --topic news --days 7 -n 10
```

## Extract Script Usage

The extract script pulls full text from web pages. This is useful when you want to read an article without visiting the website.

### Basic Extraction

**Command:**
```bash
node {baseDir}/scripts/extract.mjs "https://example.com/article"
```

**Example:**
```bash
node ~/tavily-search/scripts/extract.mjs "https://www.technologyreview.com/ai-article"
```

**What you get:**
- Full article text (not truncated)
- Clean formatting (no ads, no navigation)
- Source URL clearly labeled
- Separator lines between articles

### Multiple URLs

You can extract content from several URLs at once:

```bash
node scripts/extract.mjs "https://site1.com/article" "https://site2.com/post" "https://site3.com/page"
```

**Use cases:**
- Comparing articles on the same topic
- Building a research document
- Archiving content for offline reading

### Handling Failures

Sometimes extraction fails. The script handles this gracefully:

**Failed URLs section:**
If some URLs cannot be extracted, they appear in a "Failed URLs" section at the end. You see the URL and the error reason.

**Common failure reasons:**
- Page requires login
- Site blocks automated access
- URL returns 404 (not found)
- Content is behind a paywall

## Search Routing Strategy

You have multiple search tools available. Here is when to use each one:

### Use Tavily When:

**Citation-Heavy Research:**
Writing academic papers or reports that need proper sources. Tavily provides clean citations and source URLs.

**AI Content Generation:**
Feeding search results into AI systems. Tavily's clean formatting works better than raw HTML.

**Deep Research:**
Complex topics requiring thorough investigation. Use the `--deep` flag for comprehensive results.

**Content Extraction:**
Reading articles without visiting websites. The extract feature saves time.

**News Monitoring:**
Tracking current events with the `--topic news` option.

### Use Brave Search When:

**Broad Discovery:**
Exploring new topics where you do not know what to look for. Brave finds diverse sources quickly.

**Quick Fact-Checking:**
Verifying simple facts or definitions. Brave is faster for basic lookups.

**No API Key Available:**
Brave works without API keys for basic usage.

### Use Browser Automation When:

**Interactive Sites:**
Websites requiring login, form submission, or button clicks. Tavily cannot interact with pages.

**Dynamic Content:**
Sites that load content with JavaScript. Tavily extracts static content only.

**Visual Information:**
When you need to see images, charts, or layouts. Tavily returns text only.

### Comparison Table

| Task | Tavily | Brave | Browser |
|------|--------|-------|---------|
| Quick facts | Good | Best | Slow |
| Research with citations | Best | Good | N/A |
| Current news | Best | Good | Slow |
| Content extraction | Best | N/A | Complex |
| Logged-in sites | No | No | Yes |
| JavaScript sites | Limited | Limited | Yes |
| API required | Yes | No | No |

## Practical Examples

### Example 1: Basic Research Query

**Scenario:** You need to learn about renewable energy trends.

**Command:**
```bash
node scripts/search.mjs "renewable energy trends 2024"
```

**Result:** You get 5 results with summaries and sources. Perfect for a quick overview.

### Example 2: Deep Research Project

**Scenario:** You are writing a report and need comprehensive sources.

**Command:**
```bash
node scripts/search.mjs "machine learning in healthcare diagnosis" --deep -n 15
```

**Result:** You get 15 thoroughly researched sources with high relevance scores.

### Example 3: News Monitoring

**Scenario:** You want recent tech news from the past week.

**Command:**
```bash
node scripts/search.mjs "technology industry" --topic news --days 7 -n 10
```

**Result:** You get 10 recent news articles about technology from the last 7 days.

### Example 4: Extract Article for Reading

**Scenario:** You found an interesting article but the website has too many ads.

**Command:**
```bash
node scripts/extract.mjs "https://www.example.com/article-with-ads"
```

**Result:** You get clean text you can read in your terminal or save to a file.

### Example 5: Research Pipeline

**Scenario:** You need to research a topic, then read full articles.

**Step 1 - Search:**
```bash
node scripts/search.mjs "space exploration Mars missions" -n 5 > search_results.txt
```

**Step 2 - Identify interesting URLs from the output**

**Step 3 - Extract full articles:**
```bash
node scripts/extract.mjs "https://url1.com" "https://url2.com" > full_articles.txt
```

## Error Handling and Troubleshooting

### Error: "Missing TAVILY_API_KEY"

**What it means:**
The script cannot find your API key.

**Solutions:**

1. Check that .env file exists:
   ```bash
   ls -la .env
   ```

2. Verify the key is in the file:
   ```bash
   cat .env
   ```

3. Make sure you loaded the variables:
   ```bash
   set -a && source .env && set +a
   ```

4. Test the variable:
   ```bash
   echo $TAVILY_API_KEY
   ```

### Error: "Rate limit exceeded"

**What it means:**
You have used your 1,000 free API calls for the month.

**Solutions:**

1. Wait until next month (resets automatically)
2. Upgrade to a paid Tavily plan
3. Use Brave Search as a fallback

### Error: "Tavily Search failed (401)"

**What it means:**
Your API key is invalid or expired.

**Solutions:**

1. Log in to Tavily dashboard and verify your key
2. Generate a new key if needed
3. Update your .env file with the correct key

### Error: "No results found"

**What it means:**
Tavily could not find relevant content for your query.

**Solutions:**

1. Try a broader search term
2. Check your spelling
3. Remove special characters
4. Try synonyms for your keywords

### Error: "Failed to extract content"

**What it means:**
The extract script could not read the URL.

**Common causes:**
- Website blocks automated access
- Page requires login
- URL is incorrect
- Site uses heavy JavaScript

**Solutions:**

1. Try a different URL
2. Use browser automation for difficult sites
3. Check that the URL works in your browser

## Integration with OpenClaw

OpenClaw agents use Tavily through these scripts. Here is how it works:

### Search Integration

**You say:** "Research the latest developments in AI"

**Agent does:**
1. Recognizes this as a research query
2. Runs: `node scripts/search.mjs "latest AI developments" -n 10`
3. Parses the results
4. Presents findings with source citations

### Extract Integration

**You say:** "Read this article for me: https://example.com/article"

**Agent does:**
1. Identifies the URL
2. Runs: `node scripts/extract.mjs "https://example.com/article"`
3. Returns the clean text
4. Optionally summarizes it for you

### Smart Routing

The agent automatically chooses the right tool:

- Research questions -> Tavily Search
- "Read this URL" -> Tavily Extract
- Quick facts -> Brave Search
- Complex browsing -> Browser automation

### Combining with Other Skills

Tavily works well with other OpenClaw skills:

**Research + Summarize:**
```
1. Tavily finds sources
2. Extract pulls full text
3. Summarize YouTube processes any video links
4. Agent compiles final report
```

**News Monitoring:**
```
1. Tavily searches with --topic news
2. Results feed into memory system
3. Agent alerts you to important updates
```

## Best Practices

**1. Start with Basic Search**
Always try a basic search first. Only use `--deep` if you need more comprehensive results.

**2. Use Appropriate Result Counts**
More results are not always better. Start with 5, increase if needed.

**3. Check Relevance Scores**
Pay attention to the percentage scores. Higher scores mean more relevant content.

**4. Verify Important Facts**
Always click through to sources for critical information. Do not rely solely on AI summaries.

**5. Monitor Your Usage**
Keep an eye on your 1,000 monthly calls. Plan ahead for heavy research periods.

**6. Combine with Extract**
When search results look promising, use extract to read full articles.

**7. Use News Topic for Current Events**
The `--topic news` filter is essential for time-sensitive research.

## Advanced Tips

### Piping Search Results

Send Tavily output to other tools:

**Save to file:**
```bash
node scripts/search.mjs "query" > research.txt
```

**Count results:**
```bash
node scripts/search.mjs "query" -n 20 | grep -c "http"
```

**Extract all URLs:**
```bash
node scripts/search.mjs "query" | grep "http" | sed 's/.*http/http/'
```

### Batch Processing

Create a script for multiple searches:

```bash
#!/bin/bash
queries=(
  "renewable energy solar"
  "renewable energy wind"
  "renewable energy hydro"
)

for q in "${queries[@]}"; do
  echo "=== $q ===" >> results.txt
  node scripts/search.mjs "$q" >> results.txt
  echo "" >> results.txt
done
```

## Conclusion

Tavily Search provides AI-optimized web search that outperforms traditional engines for research tasks. With clean formatting, built-in citations, content extraction, and generous free limits, it is an essential tool for any knowledge worker.

Remember the key commands:
- `node scripts/search.mjs "query"` for web search
- `node scripts/extract.mjs "URL"` for article extraction
- Use `--deep` for comprehensive research
- Use `--topic news` for current events
- Keep your API key in .env

With Tavily integrated into OpenClaw, you have a powerful research assistant at your command. Whether you need quick facts or deep analysis, Tavily delivers the information you need in a format AI can use immediately.
