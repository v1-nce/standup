# API

18 endpoints — 15 now, 3 later. Base URL `http://127.0.0.1:8000`. Every error body is
`{"detail": str}`; a malformed request body is `422`.

A project holds one deck, one conversation, and the resources it was given. A deck is created
only by sending a message.

Anything that calls the model runs in the background: the request returns `202 {"job_id"}`, the
client polls `GET /jobs/{job_id}` until the state leaves `running`, then re-reads whatever the
job touched. Only failures that can be seen before the work starts — no project, no key — come
back on the original request; everything else surfaces as a failed job.

Endpoints marked **new**, **changed** or **later** are proposed and do not exist in the code yet;
the rest ship today.

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

    Description: Registers a codebase by local path or git URL, cloning remote sources
                 synchronously.
    Endpoint:    POST /projects
    Input:            {
                        "name":     str,
                        "location": str
                      }
    Outputs:     201  Project {
                        "id":         str,
                        "name":       str,
                        "created_at": datetime,
                        "source": {
                          "kind":     "local" | "remote",
                          "location": str,
                          "has_git":  bool
                        }
                      }
                 400  already registered, or not a directory
                 502  git clone failed

---

## 6. Read project

    Description: Reads one project.
    Endpoint:    GET /projects/{project_id}
    Input:       none
    Outputs:     200  Project
                 404  no such project

---

## 7. Rename project — **new**

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

## 10. Send a message — **changed**

    Description: Appends the message and starts answering it, rebuilding the project's deck if
                 the message asked for one.
    Endpoint:    POST /projects/{project_id}/chat
    Input:            {
                        "content": str
                      }
    Outputs:     202  {"job_id": str}
                 404  no such project
                 409  this project is already working
                 503  no key configured

---

## 11. Job status — **new**

    Description: Reports how a background job is going, and why it failed if it did.
    Endpoint:    GET /jobs/{job_id}
    Input:       none
    Outputs:     200  {
                        "id":      str,
                        "state":   "running" | "done" | "failed",
                        "step":    str,
                        "detail":  str | null
                      }
                 404  no such job

---

## 12. Read deck — **changed**

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
                        "brief": null,
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

## 13. Edit selection — **changed**

    Description: Replaces the selection with the given ids in the given order, applied
                 literally and without a model call.
    Endpoint:    PUT /projects/{project_id}/deck/selection
    Input:            {
                        "keep": [str]
                      }
    Outputs:     200  Deck
                 404  no such project, deck, or candidate id

---

## 14. Build deck — **changed**

    Description: Starts writing the slides and the `.pptx`, using one model call unless the
                 edit only dropped or reordered.
    Endpoint:    POST /projects/{project_id}/deck/build
    Input:       none
    Outputs:     202  {"job_id": str}
                 404  no such project, or no deck yet
                 409  this project is already working
                 503  no key configured

---

## 15. Download deck — **changed**

    Description: Returns the built `.pptx`.
    Endpoint:    GET /projects/{project_id}/deck/file
    Input:       none
    Outputs:     200  .pptx
                      application/vnd.openxmlformats-officedocument.presentationml.presentation
                 404  no such project or deck, or it has not been built

---

## 16. List context — **later**

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

## 17. Add context — **later**

    Description: Registers one more resource — a repository path, a PDF, a document — and
                 indexes it.
    Endpoint:    POST /projects/{project_id}/context
    Input:            {
                        "location": str
                      }
    Outputs:     202  {"job_id": str}
                 400  unreadable, unsupported, or already registered
                 404  no such project

---

## 18. Remove context — **later**

    Description: Unregisters a resource and drops everything derived from it.
    Endpoint:    DELETE /projects/{project_id}/context/{resource_id}
    Input:       none
    Outputs:     204  empty
                 404  no such project or resource
