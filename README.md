# Insegnante Interattivo — MCP Study Assistant

An AI-powered study assistant that turns your PDF materials into interactive, adaptive quizzes — running entirely as an MCP server inside [OpenCode](https://opencode.ai) (or any MCP-compatible client).

No external APIs needed. The AI that's already running in your client **is** the engine.

---

## What it does

1. **Indexes your PDFs** — extracts and chunks text from any PDF you provide
2. **Generates contextual quizzes** — the AI reads your material and writes questions with realistic, grounded answer options (not generic placeholders)
3. **Evaluates answers** — tracks correct/incorrect answers and explains mistakes using the actual source material
4. **Adapts over time** — identifies which concepts you struggle with across sessions and focuses follow-up quizzes on those gaps
5. **Lets you limit scope** — every tool accepts `material_ids` so you can restrict quizzes to specific documents

---

## Requirements

- Python 3.11+
- OpenCode (or any MCP client with stdio transport support)
- Node.js

---

## Installation

```bash
git clone https://github.com/NicCaterino/MCP_AdaptiveTutor
cd MCP_AdaptiveTutor
pip install -r requirements.txt
```

---

## OpenCode Setup

Add the server to your OpenCode config at `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "insegnante": {
      "type": "local",
      "command": ["python", "-m", "src.server"],
      "cwd": "/absolute/path/to/insegnante-interattivo-mcp",
      "enabled": true
    }
  }
}
```

On **Windows**, use the included `run.bat` instead:

```json
{
  "mcp": {
    "insegnante": {
      "type": "local",
      "command": ["C:/path/to/MCP_AdaptiveTutor/run.bat"],
      "enabled": true
    }
  }
}
```

Restart OpenCode — the tools will be available immediately. You will see a list of command with the prefixes 'insegnante_interattivo such as '/insegnante_interattivo:list_materials_prompt '

---

## How to use

### 1. Add your study materials

Drop a PDF into the `materials/` folder, then in OpenCode:

> *"Add the material materials/my-notes.pdf"*

Or scan the whole folder at once:

> *"Scan the materials folder and add all PDFs"*

### 2. Start a quiz

> *"Start a quiz"* — triggers the `/start-quiz` prompt

The AI will:
- Show your available materials
- Ask whether you want a **standard** quiz or an **adaptive** one
- Load the material content via `get_quiz_context`
- Generate questions itself, grounded in your actual PDFs
- Walk you through the quiz one question at a time
- Explain every wrong answer using the source text
- Show your final score

### 3. Adaptive quizzes

After completing one or more sessions, the adaptive mode analyses your error history and **targets the concepts you got wrong most often**.

> *"Start an adaptive quiz on material 1"*

### 4. Search your materials

> *"Search for 'attention mechanism' in my materials"*

### 5. Review past sessions

> *"Review my quiz session 3"*

---

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `list_materials` | List all indexed PDFs |
| `add_material(filepath)` | Index a new PDF |
| `scan_and_add_materials(folder_path?)` | Bulk-index a folder of PDFs |
| `search_content(query, material_id?, limit?)` | Full-text search across indexed content |
| `get_quiz_context(material_ids, adaptive?)` | Fetch material content (+ weak concepts if adaptive) for AI-driven question generation |
| `create_quiz_session(material_ids, questions)` | Save AI-generated questions and open a session |
| `get_question(session_id)` | Get the next unanswered question |
| `evaluate_answer(question_id, user_answer)` | Record answer and return correctness + context |
| `get_session_summary(session_id)` | Get score and full answer breakdown |

---

## How adaptive learning works

Every answered question is stored with its concept tag. When you call `get_quiz_context` with `adaptive=true`, the server:

1. Queries all past sessions for the selected materials
2. Calculates the error rate per concept
3. Returns the weakest concepts to the AI
4. The AI generates questions that prioritize those concepts

The loop is: **quiz → errors saved → adaptive quiz → errors updated → repeat** until your weak spots disappear.

---

## Project structure

```
MCP_AdaptiveTutor/
├── src/
│   ├── server.py        # MCP tools and prompts
│   ├── quiz.py          # Session logic, weak concept analysis
│   ├── database.py      # SQLAlchemy models
│   ├── pdf_loader.py    # PDF extraction and chunking
│   └── search.py        # Full-text search
├── materials/           # Drop your PDFs here
├── data/                # SQLite database (auto-created)
├── requirements.txt
└── run.bat              # Windows launcher
```

---

## Roadmap

- [ ] Concept mastery threshold (mark a concept as "learned" after N correct answers)
- [ ] Multi-user sessions
- [ ] Support for additional document formats (DOCX, Markdown)
- [ ] Progress dashboard

---

## License

MIT
