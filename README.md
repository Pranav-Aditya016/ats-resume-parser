# ATS Resume Parser

Deployment-ready Mistral batch parser for any number of resumes.

## Run

1. Put PDF, DOCX, PNG, JPG, or JPEG resumes in `resumes/`.
2. Set `MISTRAL_API_KEY` in `.env`.
3. Install the dependencies into Python 3.11+:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```

4. Run the parser:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\run_parser.ps1
   ```

The parser accepts any number of supported files and writes one JSON file per candidate to `parsed_resumes/`, plus `resume_summary.csv`, `resume_results.xlsx`, `batch_metrics.json`, and `parser.log`. Failed files, if any, are recorded in `failures.json`.

## Pipeline

Every resume moves through two stages:

1. **Transcription** (`ats_parser/text_extraction.py`) turns the source document into
   Markdown. DOCX is converted locally; PDF and image files go through the provider's
   OCR or document-vision model.
2. **Structuring** (`ats_parser/providers.py`) turns that Markdown into a canonical ATS
   record. Providers never see the source document, only the Markdown.

The intermediate Markdown is written to `parsed_resumes/markdown/<name>.md` with YAML
front matter recording the source file, extractor, model, page count, and timestamp. It
is the audit trail for an extraction and the corpus for downstream retrieval.

Because the two stages are separate, adding an OCR engine means implementing
`TextExtractor` and registering it in `create_extractor` — no provider, schema, or
exporter changes.

> Extracted Markdown contains the full text of a resume, including personal contact
> details. It is git-ignored by default; keep it that way.

To re-run without reprocessing valid existing JSON results (Markdown already extracted
is reused, so a rerun never pays for OCR twice):

```powershell
powershell -ExecutionPolicy Bypass -File .\run_parser.ps1 -Resume
```

You can specify different input/output folders or a Mistral model when needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_parser.ps1 -InputDir .\incoming_resumes -OutputDir .\parsed_resumes -Model mistral-small-latest
```

## Models

- **Transcription, Mistral:** `mistral-ocr-latest` (override with `MISTRAL_OCR_MODEL` in `.env`).
- **Transcription, Gemini:** document vision on the configured `GEMINI_MODEL`.
- **Transcription, DOCX:** converted locally with `python-docx`. No API call, no cost.
- **Structuring:** `mistral-small-latest` or `gemini-3.5-flash` (override with `MISTRAL_MODEL` /
  `GEMINI_MODEL` in `.env`, or `-Model`).

## Tests

```powershell
python -m unittest discover -s tests -t .
```
