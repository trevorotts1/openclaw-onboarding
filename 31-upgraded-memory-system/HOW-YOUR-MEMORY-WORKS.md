# How Your AI Memory System Works

Your AI assistant has an 8-layer memory system. Each layer solves a different problem. They all work together automatically. Here is what each one does and why it matters.

---

## Layer 1: Your Files

Your assistant stores important information in files on your computer. There are two types:

- **MEMORY.md** is the long-term file. It holds permanent information like your preferences, important decisions, project status, and lessons learned. Think of it like a notebook that never gets thrown away.

- **Daily logs** are short-term files that capture what happens each day. They are stored in a folder called memory/ with one file per day. These are like a daily journal.

**Why it matters:** Without these files, your assistant would forget everything between conversations.

---

## Layer 2: Smart Saving

When a conversation gets long, your assistant needs to make room for new information. Before it does, it automatically saves the important parts to your daily log file.

It knows to save things like:
- Decisions you made
- People and relationships mentioned
- Credentials and accounts discussed
- Project updates
- Mistakes and how they were fixed
- Deadlines and commitments

It also knows NOT to save small talk, greetings, or things already saved before.

**Why it matters:** Without smart saving, your assistant would lose important context from long conversations.

---

## Layer 3: Conversation History Search

Your assistant can search through past conversations, not just the current one. If you talked about something last week, it can find it.

This works automatically. When you ask a question, your assistant checks previous conversations for relevant context before responding.

**Why it matters:** Without this, your assistant only knows what happened in today's conversation.

---

## Layer 4: Intelligent Search

Your files are searchable using Google's Gemini Embedding 2 technology. This is not a simple keyword search. It understands meaning.

For example, if you search for "marketing budget," it will also find notes about "ad spend," "campaign costs," or "quarterly marketing allocation" even if those exact words were not in your search.

It works with markdown documents, images, and audio files.

**Why it matters:** As your knowledge base grows, simple search stops working. Intelligent search finds what you need even when you do not remember the exact words.

---

## Layer 5: Automatic Memory (memory-core)

Your assistant automatically notices and remembers important information during conversations. It does not wait for you to say "remember this." It captures things like preferences, decisions, and facts on its own.

When you start a new conversation, it automatically recalls relevant memories before responding. You do not need to remind it.

This layer uses OpenClaw's native memory-core system, which replaced the legacy memory plugin.

**Why it matters:** Without this, you would have to repeat yourself every time you start a new conversation.

---

## Layer 6: Graph Knowledge (Cognee)

Cognee creates a graph database of relationships between facts, people, projects, and concepts. Instead of just finding documents, it can answer complex questions like "What projects is Sarah working on that involve marketing budgets?"

It connects the dots between separate pieces of information that might never appear in the same document.

**Why it matters:** Simple search finds documents. Graph knowledge finds answers that span multiple documents and relationships.

---

## Layer 7: Obsidian Vault (Structured Notes)

Your assistant maintains an Obsidian-compatible vault with structured notes, wikilinks between related concepts, and frontmatter metadata. This makes it easy to browse and explore your knowledge base visually.

Daily notes capture what happened each day. Topic notes organize information by subject. Wikilinks connect related ideas.

**Why it matters:** A well-organized vault makes your knowledge browseable and discoverable, not just searchable.

---

## Layer 8: Wiki System (Collaborative Docs)

The wiki system provides deterministic pages with managed blocks and source-backed updates. Unlike free-form notes, wiki pages follow a structure that ensures consistency and enables collaboration.

Changes are tracked, sources are cited, and updates follow a predictable pattern. This is ideal for documentation that multiple people (or agents) might edit.

**Why it matters:** Structured documentation with provenance tracking ensures information stays accurate and attributable.

---

## How They Work Together

Here is an example of all 8 layers working at once:

You ask your assistant: "What did we decide about the marketing budget last week?"

1. **Layer 1** has the permanent notes in MEMORY.md
2. **Layer 2** saved the conversation details to last week's daily log when the conversation ended
3. **Layer 3** searches through last week's actual conversation transcript
4. **Layer 4** uses intelligent search to find related notes across all your files
5. **Layer 5** automatically recalled relevant memories before you even finished typing
6. **Layer 6** (Cognee) checks if there are related projects, people, or budget connections
7. **Layer 7** (Obsidian Vault) looks for any linked notes about marketing or budgets
8. **Layer 8** (Wiki System) checks for any formal documentation about budget decisions

Your assistant combines all of this to give you a complete, accurate answer.

---

## Maintenance

Your assistant handles most maintenance automatically. Two things happen periodically:

- **MEMORY.md cleanup**: When the file gets very long (over 1500 lines), old or redundant entries are consolidated to keep it manageable.
- **Daily log pruning**: Logs older than 90 days are cleaned up to save space.

Your assistant will tell you before making any major changes to these files.

---

## If Something Seems Wrong

If your assistant seems to be forgetting things or not finding information it should know:

1. Ask it: "Check your memory system status"
2. It will test each layer and report what is working and what is not
3. Most issues are fixed by typing `/restart` in Telegram

If a restart does not fix it, ask your assistant to run a full memory diagnostic.
