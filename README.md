## Toxindex Custom Task Template

This repository is a minimal template for implementing a custom Celery task that runs inside the toxindex.com workflow engine. Use it to adapt your own logic, tools, or model calls and submit a pull request to contribute your task.

### What this template includes
- A starter Celery task in `task_template_v1.py` demonstrating:
  - Receiving a payload with `task_id`, `user_id`, and a `payload` field
  - Emitting progress updates visible in the toxindex UI
  - Sending a chat-style message back to the task
  - Creating and uploading a Markdown result file to GCS and emitting it to the frontend

### File of interest
- `task_template_v1.py`: Replace the placeholder logic with your implementation. The Celery task is defined as `toolname` and is queued on `queue='toolname'`. Rename this and the queue to match your tool name.

### How to implement your custom task
1. Rename the task and queue
   - Change `@celery.task(bind=True, queue='toolname')` and the function name `toolname` to your tool name.

2. Wire your logic
   - Replace the placeholder call `yourtool_function(user_query)` with your function or integration.
   - The input text comes from `payload.get("payload")`. If your task needs files, see how the sample fetches a `File` record and downloads it from GCS.

3. Emit output to the user
   - Use the provided helpers already imported in the template:
     - Status updates: `emit_status(task_id, "your message")`
     - Chat message: build a `MessageSchema` and call `emit_task_message(...)`
     - File output: write a temporary file, upload with `GCSFileStorage().upload_file(...)`, then `emit_task_file(...)`

4. Return and finish
   - Mark completion via `Task.mark_finished(task_id)` as shown. Keep the try/except so failures correctly surface to the platform.

### Local testing (lightweight)
While the full toxindex stack provides the Celery app, models, and storage, you can still validate your core logic locally:
- Extract your core function (the part you would put into `yourtool_function`) into a plain Python function and test it with inputs.
- Keep the platform-specific calls (emit, storage, models) inside the task wrapper so your logic remains testable without the platform.

### Submission
1. Fork or clone your repository containing your implementation.
2. Copy your task code into this template structure, ensuring `task_template_v1.py` contains your adapted task.
3. Open a Pull Request against our template repository with a clear description of your task and any runtime needs.

### Notes and tips
- Minimal required payload fields: `task_id`, `user_id`. Your input text is expected in `payload`.
- If your task produces a file, prefer Markdown for easy in-UI preview; set `content_type='text/markdown'` when uploading.
- Keep logs and status messages concise and user-friendly.

### Support
Currently available built-in integrations on the platform include OpenAI, Google Gemini, and Google Search. If you need additional API keys/integrations, reach out to us; we’re expanding support and will add self-service API key registration soon.
