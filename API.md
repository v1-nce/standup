# API

17 endpoints — 14 built, 3 later. Base URL `http://127.0.0.1:8000`. Every error body is
`{"detail": str}`; a malformed request body is `422`.

A project holds one deck, one conversation, and the resources it was given. **The only thing that
calls the model is sending a message**, and it is the only way a deck is created or changed.
Reading, editing and rendering a deck are deterministic.

Sending a message returns `202` with a `Job`; the client polls `GET /jobs/{job_id}` until the
state leaves `running`, then re-reads the chat and the deck. Only failures visible before the
work starts — no project, no key, already busy — come back on the original request; everything
else surfaces as a failed job.

Endpoints marked **later** are reserved and not built.

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
                 yet. Resources are attached afterwards — endpoint 16.
    Endpoint:    POST /projects
    Input:            {"name": str}
    Outputs:     201  Project {
                        "id":         str,
                        "name":       str,
                        "created_at": datetime,
                        "source":     null | {
                          "kind":     "local" | "remote",
                          "location": str,
                          "has_git":  bool
                        }
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

## 15. List context — **later**

    Description: Lists the resources a project draws on.
    Endpoint:    GET /projects/{project_id}/context
    Input:       none
    Outputs:     200  [Resource {
                        "id":       str,
                        "kind":     "codebase" | "document",
                        "location": str,
                        "added_at": datetime
                      }]
                 404  no such project

---

## 16. Add context — **later**

    Description: Registers one more resource — a repository path, a PDF, a document — and
                 indexes it.
    Endpoint:    POST /projects/{project_id}/context
    Input:            {
                        "location": str
                      }
    Outputs:     202  Job
                 400  unreadable, unsupported, or already registered
                 404  no such project

---

## 17. Remove context — **later**

    Description: Unregisters a resource and drops everything derived from it.
    Endpoint:    DELETE /projects/{project_id}/context/{resource_id}
    Input:       none
    Outputs:     204  empty
                 404  no such project or resource
