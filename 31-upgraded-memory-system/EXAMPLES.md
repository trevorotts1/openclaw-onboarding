# Upgraded Memory System - Examples

## Example: Memory Flush Output

When the context window fills up, the agent automatically writes a note like this:

```markdown
## Session Note - March 18, 2026

- **Decision:** Replaced QMD search engine with Google Gemini Embedding 2 across both repos
- **People:** Trevor approved the migration, wants it tested on VPS next
- **Credentials:** GOOGLE_API_KEY is set in ~/.zshrc
- **Project status:** Mac repo pushed (commit 478e7be), VPS repo pushed (5d450b3)
- **Open question:** Whether to add Cognee (Layer 6) as optional skill for clients
- **Deadline:** Migration guide needs to be ready before next client onboarding (March 25)
```

Notice the categories: decisions, people, credentials, project status, open questions, deadlines. The improved flush prompt tells the agent to look for these specifically.

## Example: Memory Search

User asks: "What did we decide about the Cognee layer?"

The agent searches memory and finds:
- From MEMORY.md: "Layer 6 (Cognee) is optional. Layers 1-5 are the core package."
- From memory/2026-03-18.md: "Cognee runs as sibling Docker container. Not Docker-in-Docker."
- From a past session: Discussion about Cognee auth tokens and the bridge script.

The agent synthesizes all three sources into one answer.

## Example: Mem0 Auto-Capture

During a conversation, you mention: "My sister Lykisha's number changed to 240-555-1234."

You did not tell the agent to remember this. But Mem0 auto-captured it. Next week when you say "Text my sister," the agent already knows the new number.

## Example: Session Indexing

You had a conversation two weeks ago about setting up a Zoom meeting with a specific client. Today you ask: "What was that Zoom meeting we set up for Dr. Tola?"

Without session indexing, the agent would have no idea. With it enabled, the agent searches past sessions and finds the exact conversation with meeting details.

## Example: Prerequisite Pending

If GOOGLE_API_KEY is not set during installation:

```
Agent: "I've installed the Upgraded Memory System skill files. Layers 1, 2, 3, and 5
are active. Layer 4 (Gemini search) is PENDING because GOOGLE_API_KEY is not set.

To complete Layer 4:
1. Go to https://aistudio.google.com/app/apikey
2. Create a key
3. Add to ~/.zshrc: export GOOGLE_API_KEY='AIza...'
4. Run: source ~/.zshrc
5. Tell me 'Layer 4 is ready' and I will finish the setup."
```
