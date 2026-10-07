# Nuclear Notes & Active Recall Dashboard

A lightweight local dashboard for recording exam mistakes, searching the local question bank, and publishing reviewed notes to subject-wise Markdown files.

## Run locally

1. Use Python 3.10 or newer.
2. Install Flask:

   ```sh
   python -m pip install -r requirements.txt
   ```

3. Start the dashboard from the repository root:

   ```sh
   python app.py
   ```

4. Open <http://127.0.0.1:5000>.

The app stores unapproved notes in `drafts.json`. After saving and reviewing a draft, choose **Approve & Publish** to add it to `capsule/<subject>.md`. Existing capsule notes are preserved.

The question bank search checks `question_bank.csv` in the project root and then the repository's existing `Refinary /question_bank.csv`. Use **Use in note & preview** on a search result to copy its question, answer, and source into a new note and show them in the Markdown preview. To use a different local CSV, set `QUESTION_BANK_CSV` before starting the app.

Drafts can be saved through `/api/drafts` using the dashboard field names or through `/api/draft` using the `stem` and `concept` aliases. If omitted, the frequency defaults to `Not sure`.

The server listens only on `127.0.0.1`; it is intended for local use. Back up `drafts.json` and the relevant `capsule/*.md` files along with your study notes.
