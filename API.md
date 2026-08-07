# API

18 endpoints, all built. Base URL `http://127.0.0.1:8000`. Every error body is
`{"detail": str}`; a malformed request body is `422`.

A project holds one deck, one conversation, and the resources it was given. **The only thing that
calls the model is sending a message**, and it is the only way a deck is created or changed.
Reading, editing and rendering a deck are deterministic.

Sending a message returns `202` with a `Job`; the client polls `GET /jobs/{job_id}` until the
state leaves `running`, then re-reads the chat and the deck. Only failures visible before the
work starts — no project, no key, already busy — come back on the original request; everything
else surfaces as a failed job. Attaching context works the same way: the resource is kept before
the job starts, so it is listed immediately and the indexing is reported separately.

---

## 1. Health

    Description: Checks the service is running.
    Endpoint:    GET /health
    Input:       none
    Outputs:     200  {"status": "ok"}

---

## 2. Model status

    Description: Reports which model provider is active, without calling it.
    Endpoint:    GET /model
    Input:       none
    Outputs:     200  {
                        "provider":    "anthropic" | "gemini" | null,
                        "model":       str,
                        "configured":  bool,
                        "via_gateway": bool
                      }

---

## 3. Model check

    Description: Sends one real call to prove the configured key reaches the model.
    Endpoint:    POST /model/check
    Input:       none
    Outputs:     200  {"ok": true, "reply": str}
                 502  provider failed
                 503  no key configured

---

## 4. List projects

    Description: Lists every registered project, newest first.
    Endpoint:    GET /projects
    Input:       none
    Outputs:     200  [Project]

---

## 5. Create project

    Description: Creates an empty project: a name, one empty deck, and nothing to talk about
                 yet. Resources are attached afterwards — endpoints 16 and 17.
    Endpoint:    POST /projects
    Input:            {"name": str}
    Outputs:     201  Project {
                        "id":         str,
                        "name":       str,
                        "created_at": datetime,
                        "resources":  [Resource]
                      }
                 400  the name is blank

---

## 6. Read project

    Description: Reads one project.
    Endpoint:    GET /projects/{project_id}
    Input:       none
    Outputs:     200  Project
                 404  no such project

---

## 7. Rename project

    Description: Changes a project's display name, leaving its id and everything derived from
                 it untouched.
    Endpoint:    PATCH /projects/{project_id}
    Input:            {
                        "name": str
                      }
    Outputs:     200  Project
                 400  empty name
                 404  no such project

---

## 8. Delete project

    Description: Deletes a project and everything derived from it.
    Endpoint:    DELETE /projects/{project_id}
    Input:       none
    Outputs:     204  empty
                 404  no such project

---

## 9. Read chat

    Description: Reads the project's conversation, oldest first.
    Endpoint:    GET /projects/{project_id}/chat
    Input:       none
    Outputs:     200  [ChatMessage {
                        "role":    "user" | "assistant",
                        "content": str,
                        "at":      datetime
                      }]
                 404  no such project

---

## 10. Send a message

    Description: Appends the message and starts the agent turn that answers it and changes the
                 deck.
    Endpoint:    POST /projects/{project_id}/chat
    Input:            {
                        "content": str
                      }
    Outputs:     202  Job
                 404  no such project
                 409  this project is already working
                 503  no key configured

---

## 11. Job status

    Description: Reports how a background job is going, and why it failed if it did.
    Endpoint:    GET /jobs/{job_id}
    Input:       none
    Outputs:     200  Job {
                        "id":      str,
                        "state":   "running" | "done" | "failed",
                        "step":    str,
                        "detail":  str | null
                      }
                 404  no such job

---

## 12. Read deck

    Description: Reads the project's deck: what was chosen, what was cut, and the slides once
                 it is built.
    Endpoint:    GET /projects/{project_id}/deck
    Input:       none
    Outputs:     200  Deck {
                        "selection": Selection,
                        "slides":    [Slide] | null
                      }

                      Slide {
                        "candidate_id": str,
                        "title":        str,
                        "bullets":      [str]
                      }

                      Selection {
                        "request": str,
                        "scope": {
                          "since":        datetime | null,
                          "until":        datetime | null,
                          "paths":        [str],
                          "keywords":     [str],
                          "audience":     str | null,
                          "slide_budget": int
                        },
                        "chosen": [Scored],
                        "cut":    [Scored]
                      }

                      Scored {
                        "candidate": {
                          "id":      str,
                          "title":   str,
                          "paths":   [str],
                          "commits": [str]
                        },
                        "signals": {
                          "churn":      float,
                          "recency":    float,
                          "centrality": float,
                          "emphasis":   float,
                          "affinity":   float
                        },
                        "score": float
                      }
                 404  no such project, or no deck yet

---

## 13. Edit selection

    Description: Replaces the selection with the given ids in the given order, applied literally
                 and without a model call; written slides follow it where they already exist.
    Endpoint:    PUT /projects/{project_id}/deck/selection
    Input:            {
                        "keep": [str]
                      }
    Outputs:     200  Deck
                 404  no such project, deck, or candidate id

---

## 14. Download deck

    Description: Renders the written slides to `.pptx` and returns it. No model call.
    Endpoint:    GET /projects/{project_id}/deck/file
    Input:       none
    Outputs:     200  .pptx
                      application/vnd.openxmlformats-officedocument.presentationml.presentation
                 400  no slides have been written yet
                 404  no such project, or no deck yet

---

## 15. List context

    Description: Lists what a project draws on, in the order it was attached.
    Endpoint:    GET /projects/{project_id}/context
    Input:       none
    Outputs:     200  [Resource {
                        "id":       str,
                        "kind":     "folder" | "file",
                        "name":     str,
                        "location": str,
                        "added_at": datetime
                      }]
                 404  no such project

    Note: `id` prefixes every path derived from that resource, so `standup-a1b2/src/api.py`
          and another repository's `src/api.py` can never be confused.

---

## 16. Attach by path

    Description: Attaches folders and files by path. A folder is referenced where it lives; a
                 file is copied in, exactly as an uploaded one is, so the two ways of adding a
                 document behave the same.
    Endpoint:    POST /projects/{project_id}/context
    Input:            {"locations": [str]}
    Outputs:     202  Job — the indexing, which the resource does not wait for
                 400  not a directory, or inside a folder already attached
                 404  no such project

    Note: never 409. Indexing queues behind whatever is already indexing this project, so a
          second folder can be attached while the first is still being read.

---

## 17. Upload documents

    Description: Copies one or more documents into the project and indexes them. A browser
                 never reveals a file's path, so its bytes are what arrives.
    Endpoint:    POST /projects/{project_id}/context/files
    Input:       multipart/form-data, one or more parts named `files`
    Outputs:     202  Job
                 400  a kind of file Standup cannot read, no text in it, or the identical file
                      is attached already
                 404  no such project

    Note: two documents may share a name — every repository has a README.md. Only re-uploading
          the same bytes under the same name is refused.

---

## 18. Remove context

    Description: Detaches a resource and drops its copy and everything derived from it.
    Endpoint:    DELETE /projects/{project_id}/context/{resource_id}
    Input:       none
    Outputs:     204  empty
                 404  no such project or resource

    Note: derived means the index, the uploaded copy, and the deck — every chosen item, cut item
          and written slide whose id begins with this resource, plus any rendered .pptx. Left
          behind, those ids reach the agent as evidence and read as context that still exists.
          The chat log is not touched: it is what was said, not what is attached.
