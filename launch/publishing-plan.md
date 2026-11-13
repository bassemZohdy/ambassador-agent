# Publishing and promotion plan

How to publish the pattern and get it in front of the people who can test it. Steps marked **you** need the repository owner's accounts and cannot be done from the repository.

## 1. Before anything is posted

| Step | Who | Why |
|---|---|---|
| Confirm the Actions run on `main` is green | you | The first thing a visitor checks |
| Enable GitHub Pages: Settings, Pages, "Deploy from a branch", `main`, folder `/docs` | you | Gives the guide a clean public URL: `https://bassemzohdy.github.io/ambassador-agent/` |
| Check that the four animated diagrams play on the Pages site and in the README | you | They were generated and checked against the text, but not viewed in a browser |
| Set the repository description and topics: `agentic-ai`, `design-patterns`, `integration`, `a2a`, `multi-agent` | you | Search and first impression |
| Create the labels `counter-example` and `known-use` | you | The issue templates apply them |
| Add a social preview image (a still of the architecture diagram) | you | Links shared on LinkedIn and elsewhere show it |
| Confirm your employer's policy on publishing outside work, and say in your profile or the post that this is personal work | you | Avoids the pattern being read as an official position |
| Decide whether to publish with the open questions listed | you | Recommended: listing them is what makes "tell me where it breaks" credible |

## 2. Publish the article

Publish in one place first and make every other copy point back to it.

| Order | Channel | How | Notes |
|---|---|---|---|
| 1 | dev.to or Hashnode | Paste `article.md`. Set the canonical URL to this first copy | Both take Markdown directly. Upload the diagrams as images |
| 2 | Medium | Use "Import a story" with the first copy's URL | Import sets the canonical link for you. Medium does not show SVG: export stills as PNG |
| 3 | LinkedIn article | Paste, and link to the first copy at the top | Reaches the architect audience directly |

The animated SVG diagrams play on GitHub and on the Pages site. Most publishing platforms accept PNG or GIF only, so export a still or a short recording of each for the article.

## 3. Announce it

| Day | Channel | What to post | Rule to respect |
|---|---|---|---|
| 1 | LinkedIn | The post from `posts.md`, with the architecture diagram | Reply to every comment in the first day |
| 1 | X, Mastodon, Bluesky | The short posts, one a day | |
| 2 | A2A community (discussions in the `a2aproject/A2A` repository) | A question, not an announcement: "is this extension the right way to express `deferred` and compensation?" | Maintainers respond to concrete protocol questions, not promotion |
| 2 | Communities of the agent platforms you used (Google ADK, LangGraph) | The reference adapter and what the pattern asks of a platform | Post as a user of the platform |
| 3 | Hacker News | Submit the guide URL with a plain title | No superlatives in the title. Be present for the first hours |
| 3 | Reddit: architecture and AI-agent communities | A short summary and the link | Read each community's self-promotion rule first. Many require participation before posting |
| Week 2 | Newsletters and aggregators that cover software architecture | A two-line pitch and the link | One polite message each |

## 4. Longer-running routes

| Route | What it takes | Realistic timing |
|---|---|---|
| A contributed article on a practitioner site such as InfoQ | A proposal, then an edited article. They favour experience reports | After a first real use |
| A conference or meetup talk | The abstract in `posts.md` | Next call for papers in your region |
| A public pattern catalogue | For example [Awesome agentic patterns](https://github.com/jott2121/awesome-agentic-patterns). Its criteria include that more than one team is using the pattern, a public reference, and that the entry is not a promotion | **Not yet eligible.** Come back with a known use |
| A formal A2A extension | Publish the fields in `docs/protocol-mapping.md` as an extension specification | After feedback from the A2A discussion |

## 5. What will make or break it

1. **A known use.** One documented system that works this way is worth more than every post. Apply the pattern to one real boundary and write it up.
2. **Engaging with objections.** The likely ones and short answers are in `posts.md`. Turn the real ones into an FAQ page after two weeks.
3. **Honesty about status.** It is a proposal with open questions. Say so first, before someone else does.

## 6. How to tell whether it worked

| Signal | Meaning |
|---|---|
| Issues opened with the counter-example template | People tested it against their own systems. The best outcome |
| Issues opened with the known-use template | Evidence for the pattern |
| Other articles or talks that cite it | The name is spreading |
| Stars and views | Reach only. Do not optimise for these |

## 7. Risks

| Risk | Mitigation |
|---|---|
| "This already exists" | The comparison, influences and references pages are the answer. Link them |
| The name clashes with the cloud Ambassador pattern and with existing patents | Stated openly in the comparison page. Take legal advice before any commercial use of the name |
| The reference code is read as a product | The README and `reference/README.md` say it is an illustration, with its limits |
| A2A changes | The pattern depends on stable concepts only. The mapping page names the SDK version it was checked against |
