# API

13 endpoints. Base URL `http://127.0.0.1:8000`. Every error body is `{"detail": str}`; a
malformed request body is `422`.

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

## 7. Delete project

    Description: Deletes a project and everything derived from it.
    Endpoint:    DELETE /projects/{project_id}
    Input:       none
    Outputs:     204  empty
                 404  no such project

---

## 8. Read chat

    Description: Reads the project's conversation, oldest first.
    Endpoint:    GET /projects/{project_id}/chat
    Input:       none
    Outputs:     200  [ChatMessage]
                 404  no such project

---

## 9. Append chat

    Description: Appends one message to the project's conversation.
    Endpoint:    POST /projects/{project_id}/chat
    Input:            {
                        "role":    str,
                        "content": str
                      }
    Outputs:     201  ChatMessage {
                        "role":    str,
                        "content": str,
                        "at":      datetime
                      }
                 404  no such project

---

## 10. Propose deck

    Description: Turns a request into a selection of what belongs on the slides, using one
                 model call.
    Endpoint:    POST /projects/{project_id}/decks
    Input:            {
                        "request":      str,
                        "slide_budget": int >= 1   (default 5)
                      }
    Outputs:     201  {
                        "deck_id":   str,
                        "selection": Selection
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
                 400  the window is impossible, or the project has no git history
                 404  no such project
                 502  scope call failed
                 503  no key configured

---

## 11. Read selection

    Description: Re-reads a proposed selection without recomputing it.
    Endpoint:    GET /projects/{project_id}/decks/{deck_id}
    Input:       none
    Outputs:     200  Selection
                 404  no such project or deck

---

## 12. Edit selection

    Description: Replaces the selection with the given ids in the given order, applied
                 literally.
    Endpoint:    PUT /projects/{project_id}/decks/{deck_id}/selection
    Input:            {
                        "keep": [str]
                      }
    Outputs:     200  Selection
                 404  no such project, deck, or candidate id

---

## 13. Build deck

    Description: Writes the slides and returns the deck file, using one model call unless the
                 edit only dropped or reordered.
    Endpoint:    POST /projects/{project_id}/decks/{deck_id}/build
    Input:       none
    Outputs:     200  .pptx
                      application/vnd.openxmlformats-officedocument.presentationml.presentation
                 404  no such project or deck
                 502  plan call failed, or the plan could not be grounded
                 503  no key configured
