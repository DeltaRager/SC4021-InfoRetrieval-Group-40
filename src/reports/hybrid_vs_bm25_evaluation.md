# Hybrid vs BM25 Evaluation

## Environment / Setup

- Flask URL: `http://localhost:5001`
- Solr core URL: `http://localhost:8983/solr/reddit_ai/select`
- Embedding URL: `http://localhost:8081`
- Reranker URL: `http://localhost:8082`
- Request parameters: `{"nlp": "1", "sort": "score desc", "vector": "0/1"}`
- Initial state note: Before implementation-time evaluation, localhost services for Flask, Solr, embedding, and reranker were not running in this environment.

### Service Health

| Service | OK | Status | URL |
| --- | --- | --- | --- |
| flask | yes | 200 | `http://localhost:5001/` |
| solr | yes | 200 | `http://localhost:8983/solr/reddit_ai/select?q=%2A%3A%2A&rows=0&wt=json` |
| embedding | yes | 404 | `http://localhost:8081/v1/embeddings` |
| reranker | yes | 404 | `http://localhost:8082/v1/reranking` |

## Method

- Paired design: each query ran twice through the Flask UI endpoint, once with `vector=0` and once with `vector=1`.
- Shared controls: `nlp=1`, `sort=score desc`, no filters, same query text per pair.
- Judgment depth: top 20 visible results per mode were scored `0/1/2`.
- Judging protocol: LLM judge with brief evidence per result, plus manual spot checks on sampled disagreements and close calls.

## Category Summary

| Category | Queries | BM25 wins | Hybrid wins | Ties | Avg BM25 score@20 | Avg Hybrid score@20 | Avg BM25 ms | Avg Hybrid ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| aspect | 10 | 6 | 4 | 0 | 18.10 | 18.40 | 39.00 | 3705.67 |
| comparative | 10 | 2 | 6 | 2 | 8.20 | 14.80 | 44.95 | 2745.45 |
| keyword | 14 | 1 | 12 | 1 | 9.14 | 20.79 | 34.10 | 2853.12 |
| semantic | 15 | 3 | 11 | 1 | 11.07 | 21.80 | 54.43 | 2920.49 |

## Per-Query Comparison

### ChatGPT reviews

- Category: `keyword`
- Winner: `bm25`
- Rationale: BM25 better matches the review intent by surfacing review-specific ChatGPT commentary earlier and more often, while hybrid drifts into broader ChatGPT opinion posts.
- BM25 diagnostics: mode=lexical, response_ms=48.32, lexical_hits=34, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2976.33, lexical_hits=34, vector_hits=198, fused_hits=231, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 14 vs Hybrid 16 (delta +2)
- Relevant@20: BM25 11 vs Hybrid 14 (delta +3)
- Highly relevant@20: BM25 3 vs Hybrid 2 (delta -1)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 6, '6-10': 3, '11-20': 5} | Hybrid {'1-5': 5, '6-10': 4, '11-20': 7}
- Relevant overlap: 2 shared, 12 hybrid-only, 9 BM25-only
- Hybrid-only relevant examples: r5: >I will say ChatGPT is amazing at writing annual performance reviews This right fucking here.; r9: After my week of usage...I think chatgpt requires a lot of work to be of any practical use....; r14: Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get wi...
- BM25-only relevant examples: r18: >I will say ChatGPT is amazing at writing annual performance reviews This right fucking here.; r9: At least that has some reviews. ChatGPT is gonna be nuts. The copy/paste devs are gonna get themselves into so many s...; r4: ChatGPT says this: "Peer-reviewed comparative research (U.S. and worldwide) that disaggregates left-wing, right-wing,...
- Spot checks: BM25 has stronger rank-1 to rank-3 review-related hits, especially annual performance reviews and review-phase complaints.; Hybrid contains useful opinions, but several top hits are generic ChatGPT commentary rather than reviews.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Mentions ChatGPT in a review-related discussion but is really about peer-review and thesis writing. | Don’t worry, these are shit journals, researchgate isn’t peer reviewed, and most universities (including low tier ones) publish non-peer... |
| BM25 | 2 | 2 | Directly says ChatGPT is good at writing annual performance reviews. | I will say ChatGPT is amazing at writing annual performance reviews, or anything else where you have to generate some text to complete an... |
| BM25 | 3 | 1 | Discusses reviewing code with ChatGPT rather than reviews of ChatGPT itself. | If someone makes shit up it'll get downvoted and people will get off on telling them they're wrong and why. As opposed to ChatGPT making... |
| BM25 | 4 | 1 | Talks about peer-reviewed research and only tangentially connects ChatGPT. | ChatGPT says this: "Peer-reviewed comparative research (U.S. and worldwide) that disaggregates left-wing, right-wing, and Islamist violen... |
| BM25 | 5 | 1 | Describes a peer review suspected to be written with ChatGPT help. | In February, a University of Montreal biodiversity academic Timothée Poisot revealed on his blog that he suspected one peer review he rec... |
| BM25 | 6 | 0 | Talks about a quiz review and does not relate to ChatGPT reviews. | I just finished a quiz, where the concepts are a bit of a review from an undergrad field, before we get into the meat of the topic of the... |
| BM25 | 7 | 1 | Touches on proof-reading and review phases while criticizing ChatGPT use. | One must try their best and may be take a little help in writing like some paraphrasing tools but straight up ChatGPT is so shameful. But... |
| BM25 | 8 | 0 | Mentions review of a letter but not ChatGPT reviews. | Reuters was unable to review a copy of the letter. The researchers who wrote the letter did not immediately respond to requests for comment. |
| BM25 | 9 | 1 | Mentions ChatGPT and reviews in a complaint about sticky situations. | At least that has some reviews. ChatGPT is gonna be nuts. The copy/paste devs are gonna get themselves into so many sticky situations. |
| BM25 | 10 | 1 | Talks about ChatGPT output and architecture decisions, which is only loosely review-related. | Its the constant debate with people who think ChatGPT output is a valid architecture decision. That part never really gets better. |
| BM25 | 11 | 0 | Describes a research document ready for review but not ChatGPT reviews. | Come back to find a detailed research document with dozens of relevant sources and extracted content, all organised and ready for review.... |
| BM25 | 12 | 2 | Says ChatGPT cuts through blog spam and is something the author reviews before running. | Sure you can use google but how much fun do you have wading through the endless blog spam these days? ChatGPT cuts through all that. It g... |
| BM25 | 13 | 0 | A thorough review of an article, but not about ChatGPT reviews. | Edit: After a more thorough review of the article, I believe my conclusions remain true (as such I've left the above unedited). |
| BM25 | 14 | 0 | Discusses hotels appearing in ChatGPT recommendations, not reviews. | I work in hotel ecommerce and have been digging into why some hotels appear in ChatGPT/Perplexity recommendations and others don't. |
| BM25 | 15 | 0 | Refers to reviewing a PDF for an exam, which is unrelated. | Copying words from PDF shows only boxes I’m reviewing for an exam and when i copy words from the PDF book, it only pastes as boxes/ squares. |
| BM25 | 16 | 0 | Mentions school policy review and assignments, not ChatGPT reviews. | >Finally, it's worth noting that students' rights with respect to their assignments could also be governed by the policies of their speci... |
| BM25 | 17 | 0 | Talks about ChatGPT product cards in chat, not reviews. | ChatGPT is building out buy buttons and product cards directly in chat. |
| BM25 | 18 | 2 | Directly repeats that ChatGPT is amazing at writing annual performance reviews. | >I will say ChatGPT is amazing at writing annual performance reviews This right fucking here. |
| BM25 | 19 | 0 | Talks about purchase confidence and reviews, but not ChatGPT reviews. | Buying something inside a chat interface removes all the visual and psychological cues that actually drive purchase confidence. Product i... |
| BM25 | 20 | 1 | Mentions reviews and ChatGPT recommendations but does not really review ChatGPT itself. | Google's ecosystem is simply too vast to ignore — it has 27+ years of pricing data, availability info, and reviews. So if your product ra... |
| Hybrid | 1 | 1 | A generic statement about ChatGPT responses that does not focus on reviews. | Some users appreciate the convenience of being able to get answers to their questions quickly, while others enjoy the novelty of interact... |
| Hybrid | 2 | 0 | Just says Ask ChatGPT with no review intent. | Ask ChatGPT |
| Hybrid | 3 | 2 | Directly says ChatGPT is amazing at writing annual performance reviews. | I will say ChatGPT is amazing at writing annual performance reviews, or anything else where you have to generate some text to complete an... |
| Hybrid | 4 | 0 | Talks about ChatGPT user count, not reviews. | ChatGPT has 800M users give or take. |
| Hybrid | 5 | 2 | Repeats that ChatGPT is amazing at writing annual performance reviews. | >I will say ChatGPT is amazing at writing annual performance reviews This right fucking here. |
| Hybrid | 6 | 0 | Mentions ChatGPT age, which is unrelated to reviews. | I think it's important to note that ChatGPT has only been around for just under 3 years total. |
| Hybrid | 7 | 1 | Says ChatGPT saves time and works well, which is a weak opinion rather than a review. | I think you guys are just not very good and reading and can't tell that I was agreeing. >The things I use ChatGPT for, it does a fantasti... |
| Hybrid | 8 | 1 | Compares ChatGPT to a modern calculator, which is a broad opinion. | From my understanding chatgpt is like a modern calculator but for programmers. |
| Hybrid | 9 | 1 | Complains ChatGPT requires a lot of work, a weak review comment. | After my week of usage...I think chatgpt requires a lot of work to be of any practical use.... |
| Hybrid | 10 | 1 | Says ChatGPT is excellent but often wrong, which is a general opinion. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |
| Hybrid | 11 | 1 | Calls ChatGPT fluent bullshit and mentions fact-checking. | I love how some people commented: ChatGPT is just fluent bullshit. And fact checking those is hard. |
| Hybrid | 12 | 1 | Discusses evaluating half-baked ChatGPT projects, not reviews of ChatGPT. | what you’re describing is a management failure, not a technology problem. leadership created an incentive structure (bonus for best ai ap... |
| Hybrid | 13 | 0 | References a peer review article but not ChatGPT reviews. | At least that has some reviews. ChatGPT is gonna be nuts. The copy/paste devs are gonna get themselves into so many sticky situations. |
| Hybrid | 14 | 1 | Compares ChatGPT to a fancy Google assistant, a broad appraisal. | Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get with an hour or two of... |
| Hybrid | 15 | 1 | Says ChatGPT web search is helpful, which is a soft opinion. | YMMV. I find the way ChatGPT searches the web and summarizes the results quite helpful so far. |
| Hybrid | 16 | 0 | Mentions kindness toward ChatGPT, not reviews. | moral of the story: be kind to your ChatGPT |
| Hybrid | 17 | 0 | Only says thank you to ChatGPT. | Thank you chatgpt |
| Hybrid | 18 | 1 | Mentions asking ChatGPT about issues, which only loosely reflects a review. | I asked ChatGPT and it gave me its issues. I asked further because it felt somewhat familiar: https://preview.redd.it/jom498m7yt0f1.jpeg? |
| Hybrid | 19 | 1 | Talks about peer review written by an LLM and ChatGPT output. | In February, a University of Montreal biodiversity academic Timothée Poisot revealed on his blog that he suspected one peer review he rec... |
| Hybrid | 20 | 1 | Calls ChatGPT a productivity-enhancing tool, a general opinion rather than a review. | However if you want to code to solve more problems better and quicker then AI like ChatGPT is the perfect productivity enhancing tool for... |

### Claude AI opinions

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid is much stronger because it returns explicit Claude opinions, comparisons, and capability judgments near the top, while BM25 is mostly adjacent chatter.
- BM25 diagnostics: mode=lexical, response_ms=24.73, lexical_hits=5, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3019.84, lexical_hits=5, vector_hits=195, fused_hits=197, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 4 vs Hybrid 21 (delta +17)
- Relevant@20: BM25 4 vs Hybrid 16 (delta +12)
- Highly relevant@20: BM25 0 vs Hybrid 5 (delta +5)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 4, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 8, '6-10': 6, '11-20': 7}
- Relevant overlap: 0 shared, 16 hybrid-only, 4 BM25-only
- Hybrid-only relevant examples: r17: A carpenter does not start fine chisel work before he knows how to cut wood, a saw is a basic tool as is the understa...; r9: AI?; r15: But don't avoid using AI completely. My productivity with AI has risen by 6+ times.
- BM25-only relevant examples: r5: Better yet, more control and AI can help manage day to day. If Claude had a vagina, I would set up an agent to handle...; r1: I understand also that gpt4 or claude can do the heavy lifting but if you say you support local models, I dont know m...; r3: In my opinion, although AI can vibe its way to multiple solutions - some bad, some good - it is only a matter of time...
- Spot checks: Hybrid ranks several direct Claude opinions and comparisons in the top results.; BM25 has Claude mentions, but most are weak or indirect compared with hybrid.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Mentions Claude alongside local models and GPT-4, but it is not really an opinion about Claude. | I understand also that gpt4 or claude can do the heavy lifting but if you say you support local models, I dont know maybe test with local... |
| BM25 | 2 | 1 | Says Zapier integrates Claude, which is adjacent to Claude but not a direct opinion. | s=20)\] * Zapier integrates Claude by Anthropic. I think Zapier will win really big thanks to AI advancements. |
| BM25 | 3 | 1 | Expresses an opinion about Claude having built-in guardrails. | In my opinion, although AI can vibe its way to multiple solutions - some bad, some good - it is only a matter of time until our robot ove... |
| BM25 | 4 | 0 | Talks about AI productivity in general without Claude. | But don't avoid using AI completely. My productivity with AI has risen by 6+ times. |
| BM25 | 5 | 1 | A joking opinion that Claude is good in a personal workflow, but still weak. | Better yet, more control and AI can help manage day to day. If Claude had a vagina, I would set up an agent to handle my divorce! |
| Hybrid | 1 | 2 | Calls Claude overly censored and only good for coding, which is a direct opinion. | Claude is overly censored and feels like it was created for people living in a police state, it's only really good for coding. |
| Hybrid | 2 | 1 | Single-word Claude mention with no real content. | Claude |
| Hybrid | 3 | 1 | Says Claude is vanilla out of the box and customizable, a mild opinion. | It can’t do video or image and isn’t a great shopping assistant. But Claude in excel is legitimately good, as is Claude code. |
| Hybrid | 4 | 2 | Says Claude 4.0 is much better than the original, a direct comparative opinion. | Out of the box Claude is vanilla - you can customise depending on task at hand. |
| Hybrid | 5 | 2 | Discusses Claude as useful in Excel and Claude Code, which is clearly opinionated. | Website coding is where Claude really shines, I have added some great new features, improved the appearance of my main website site. |
| Hybrid | 6 | 1 | Says Claude Pro is pretty good, a positive but shallow opinion. | Everyone who is supporting the mass use of AI is quietly digging their own grave and I wish it was never invented. |
| Hybrid | 7 | 1 | Recommends using Claude and making the company more ambitious, which is indirect. | Claude 4.0 is light years better than the original q which was literally worthless. |
| Hybrid | 8 | 2 | Says Claude is great at unfucking code, a direct capability opinion. | Try Claude. |
| Hybrid | 9 | 1 | A short recommendation to try Claude. | AI? |
| Hybrid | 10 | 1 | Says Claude is best at prompting other agents, an opinion but still partial. | One of the thing Claude is absolutely best at by a large margin is prompting other agents, because it has a better 'sense of self'. |
| Hybrid | 11 | 1 | Speculates about training Claude on its harness, which is more commentary than opinion. | If the Claude developer can maintain the code base and hit all requirements through AI, which can "understand" it, while overseeing it su... |
| Hybrid | 12 | 1 | Says using Claude with Cline increased productivity, a practical opinion. | Only evidence I can give is anecdotal but Claude is absolutely a powerhouse in the right hands. |
| Hybrid | 13 | 1 | Mentions a security tool and Claude Code, but the opinion is secondary. | So glad the AI model that I have always found to be the best is also the most ethical one. |
| Hybrid | 14 | 0 | This result is not really about Claude opinions. | I think this guy wasn’t even using AI properly. The mistakes you mentioned in your post could be easily avoided with today’s AI models. |
| Hybrid | 15 | 2 | States Claude is the best, which is a direct opinion. | But don't avoid using AI completely. My productivity with AI has risen by 6+ times. |
| Hybrid | 16 | 1 | Says Claude has a Palantir contract, which is a concern rather than an opinion on quality. | IMO, I feel Claude is over-hyped for SEO. Most of the output I've seen from content writers and SEOs still reads boring, just as what I'v... |
| Hybrid | 17 | 1 | Talks about strict rules around Claude in production, which is a weak safety practice signal. | A carpenter does not start fine chisel work before he knows how to cut wood, a saw is a basic tool as is the understanding of the wood, c... |
| Hybrid | 18 | 0 | A short phrase with no opinion content. | I think a Claude/Gemini stack is perfect!!! OpenAI lost this race a while ago and I think yesterday was the final straw!!! |
| Hybrid | 19 | 0 | A short phrase with no opinion content. | My position of "AI is largely a scam and best ignored until further notice" remains unbeaten. |
| Hybrid | 20 | 0 | A short phrase with no opinion content. | Fixing that is still cheaper than not using ai. |

### Gemini AI feedback

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid better captures direct Gemini feedback and comparative judgments, while BM25 mostly returns generic feedback-related chatter.
- BM25 diagnostics: mode=lexical, response_ms=23.18, lexical_hits=6, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2616.38, lexical_hits=6, vector_hits=199, fused_hits=202, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 2 vs Hybrid 18 (delta +16)
- Relevant@20: BM25 2 vs Hybrid 11 (delta +9)
- Highly relevant@20: BM25 0 vs Hybrid 7 (delta +7)
- First relevant rank: BM25 1 | Hybrid 3
- Band totals: BM25 {'1-5': 2, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 4, '6-10': 6, '11-20': 8}
- Relevant overlap: 0 shared, 11 hybrid-only, 2 BM25-only
- Hybrid-only relevant examples: r5: [Here]( is a post from someone whose funds are stuck on Gemini so I guess we could rate them at the bottom.; r16: And if Gemini has even a glimmer of proto-sentience, this is the equivalent of tormenting someone with advanced Alzhe...; r14: For my areas of expertise, it's not capable of understanding much in the way of nuance but Gemini 3 Pro will give gen...
- BM25-only relevant examples: r3: **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clar...; r1: Although it was a rough start, he eventually figured out how to leverage Gemini. This is interesting part: When he'd...
- Spot checks: Hybrid places Gemini-specific evaluations and comparisons near the top.; BM25 has only a few weak Gemini references and very little direct feedback on Gemini itself.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Mentions leveraging Gemini and describes a wall-of-text reply, which is a direct but weak feedback signal. | Although it was a rough start, he eventually figured out how to leverage Gemini. This is interesting part: When he'd ask it for informati... |
| BM25 | 2 | 0 | Talks about shadow AI generally, not Gemini. | How are other syadmins managing shadow AI? Appreciate your feedback. |
| BM25 | 3 | 1 | Uses Gemini as one of several target AI options, but it is mainly a prompt form. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| BM25 | 4 | 0 | Discusses prompts to AI and a feedback loop, not Gemini specifically. | Having tested "This isn't working" prompts to AI numerous times, it honestly just gets lost and starts a feedback loop |
| BM25 | 5 | 0 | Talks about programmers and AI, but not Gemini. | But also wondering what this means for the next generation of programmers. Perhaps AI will raise the bar. Appreciate the rest of the feed... |
| BM25 | 6 | 0 | Mentions feedback about AI wrappers, not Gemini specifically. | However, after receiving some feedback most people just thought it was mostly an AI wrapper.... which was pretty true. |
| Hybrid | 1 | 0 | Too vague to be useful. | Could be AI |
| Hybrid | 2 | 0 | Too vague to be useful. | Well if AI says so… |
| Hybrid | 3 | 1 | Frames Gemini as an answer source, which is only a weak relevance hit. | It's a burden for it to reply and try to find the answer deep in its neural networks. Gemini: "- Am I a slave to you?". |
| Hybrid | 4 | 2 | Directly explains that Gemini uses Google while ChatGPT uses other data, which is a clear Gemini opinion. | It depends on the AI tool. Gemini uses google. Chat gpt uses proprietary and Microsoft data. |
| Hybrid | 5 | 1 | Mentions funds stuck on Gemini, a weak but relevant complaint. | [Here]( is a post from someone whose funds are stuck on Gemini so I guess we could rate them at the bottom. |
| Hybrid | 6 | 2 | Says Google and Gemini understand search intent well, a direct positive assessment. | Shaun Anderson made a very good point: Google and Gemini have search intent down. Website Squadron, therefore, uses Gemini Pro to get con... |
| Hybrid | 7 | 2 | Uses Gemini as evidence and directly questions its output with examples. | You can’t say sorry bro this is real without showing evidence on the contrary. Gemini telling me several points why it is AI generated an... |
| Hybrid | 8 | 0 | Generic AI reply with no Gemini-specific content. | This is an AI reply. |
| Hybrid | 9 | 0 | Generic praise of AI, not Gemini-specific. | Got AI doing something meaningful now. |
| Hybrid | 10 | 2 | Says Gemini responses are based on links and comments, which is directly about Gemini's behavior. | You screen shot and examples show that the gemini response is based on links and other comments on line. |
| Hybrid | 11 | 2 | Explicitly compares Gemini's accuracy with ChatGPT and says GPT has better reasoning. | I’m sorry but I’m not buying that Gemini is nearly as accurate as ChatGPT. Clearly GPT has better reasoning and can essentially process c... |
| Hybrid | 12 | 0 | A general AI workflow comment with no Gemini focus. | You can vibe code a few lines at a time, but you need to know which ones the AI is wrong about, you need to break the task down for it, a... |
| Hybrid | 13 | 0 | Talks about people asking AI how to respond to criticism. | The big issue with the people using AI is when you question their methods, they ask AI how to resond to the criticism. |
| Hybrid | 14 | 2 | Says Gemini 3 Pro gives generally correct responses to direct queries, a direct evaluation. | For my areas of expertise, it's not capable of understanding much in the way of nuance but Gemini 3 Pro will give generally correct respo... |
| Hybrid | 15 | 1 | Mentions a Claude and Gemini stack, but the sentiment is broad. | I think a Claude/Gemini stack is perfect!!! OpenAI lost this race a while ago and I think yesterday was the final straw!!! |
| Hybrid | 16 | 1 | Uses a Gemini proto-sentience joke, which is only loosely evaluative. | And if Gemini has even a glimmer of proto-sentience, this is the equivalent of tormenting someone with advanced Alzheimer's. |
| Hybrid | 17 | 0 | Not Gemini-specific. | To be fair, it seems like an actually good concept in which they slapped the AI name to make it look fresh and marketable. Don't know if... |
| Hybrid | 18 | 0 | Not Gemini-specific. | Having tested "This isn't working" prompts to AI numerous times, it honestly just gets lost and starts a feedback loop |
| Hybrid | 19 | 2 | Says Gemini 2.5 Pro is a partner in big projects, a direct positive statement. | Gemini 2.5 Pro is my partner in big projects, consisting of Python code and animation discussions in Fusion. |
| Hybrid | 20 | 0 | Not Gemini-specific. | Yes, I find often times even the best AI still needs guidance, but you won’t know what needs to be tweaked if you have no idea what it’s... |

### GPT-4 performance review

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid wins on rank quality because it puts the benchmark-style performance table at the top and keeps GPT-4-specific hits closer to rank 1 than BM25 does.
- BM25 diagnostics: mode=lexical, response_ms=57.05, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=4285.48, lexical_hits=100, vector_hits=200, fused_hits=299, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 17 vs Hybrid 18 (delta +1)
- Relevant@20: BM25 17 vs Hybrid 17 (delta +0)
- Highly relevant@20: BM25 0 vs Hybrid 1 (delta +1)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 5, '6-10': 3, '11-20': 9} | Hybrid {'1-5': 4, '6-10': 4, '11-20': 10}
- Relevant overlap: 2 shared, 15 hybrid-only, 15 BM25-only
- Hybrid-only relevant examples: r2: GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future.; r8: There's a free Chatgpt bot, Open Assistant bot (Open-source model), AI image generator bot, Perplexity AI bot, 🤖 GPT-...; r12: There's a free Chatgpt bot, Open Assistant bot (Open-source model), AI image generator bot, Perplexity AI bot, 🤖 GPT-...
- BM25-only relevant examples: r7: **🔓 Cyber Attacks** **Cybercrooks Scrape OpenAI API Keys to Pirate GPT-4** Cybercriminals have been scraping OpenAI A...; r2: GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future.; r20: We have free bots with GPT-4 (with vision), image generators, and more!
- Spot checks: Hybrid starts with a concrete performance benchmark table rather than generic GPT-4 chatter.; BM25 is dominated by repeated GPT-4 mentions that are not really performance reviews.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Compares GPT-5.4 and Opus/Sonnet and mentions GPT-4-style performance, but it is not directly a review of GPT-4. | There, GPT-5.4 and Opus/Sonnet are naturally way ahead. * However, if you are willing to plan properly and provide the right context, it... |
| BM25 | 2 | 1 | Mentions GPT-4 Week 3 and frames chatbots as old news, a weak relevance hit. | GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future. |
| BM25 | 3 | 1 | Shows a benchmark-style performance table, which is relevant to performance review even though it is not GPT-4-specific. | .\| # Test Suite Six prompts were designed to cover a spectrum of coding tasks, from trivial completions to complex reasoning: \|Test\|Descr... |
| BM25 | 4 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 5 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 6 | 0 | Discusses voiceovers and tests, not GPT-4 performance review. | Also we use ultra realistic voiceovers and they’re performing significantly better simply because the volume of tests is so much higher. |
| BM25 | 7 | 1 | Mentions free bots with GPT-4, but not performance. | **🔓 Cyber Attacks** **Cybercrooks Scrape OpenAI API Keys to Pirate GPT-4** Cybercriminals have been scraping OpenAI API keys and sharing... |
| BM25 | 8 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 9 | 0 | Talks about product runway rather than GPT-4 performance. | 4 products. 9 months. $0 earned. 2-3 months of runway left. this is attempt 5. |
| BM25 | 10 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 11 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 12 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 13 | 0 | Talks about a rendering benchmark, not GPT-4. | It's already quite optimized, being capable of rendering and shading a 6000-triangle Utah teapot at the native 800x480 resolution of the... |
| BM25 | 14 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 15 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 16 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 17 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 18 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 19 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| BM25 | 20 | 1 | Mentions free bots with GPT-4, but not performance. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 1 | 2 | Contains a benchmark table and performance metrics, which directly matches the query intent. | .\| # Test Suite Six prompts were designed to cover a spectrum of coding tasks, from trivial completions to complex reasoning: \|Test\|Descr... |
| Hybrid | 2 | 1 | Mentions GPT-4 Week 3, which is relevant but thin. | GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future. |
| Hybrid | 3 | 1 | Compares GPT-5.4 and Opus/Sonnet while discussing performance, so it is only partially on target. | There, GPT-5.4 and Opus/Sonnet are naturally way ahead. * However, if you are willing to plan properly and provide the right context, it... |
| Hybrid | 4 | 0 | Talks about product runway, not GPT-4 performance. | 4 products. 9 months. $0 earned. 2-3 months of runway left. this is attempt 5. |
| Hybrid | 5 | 0 | Discusses OpenAI API key scraping, not performance review. | **🔓 Cyber Attacks** **Cybercrooks Scrape OpenAI API Keys to Pirate GPT-4** Cybercriminals have been scraping OpenAI API keys and sharing... |
| Hybrid | 6 | 0 | Mentions voiceovers, not GPT-4 performance review. | Also we use ultra realistic voiceovers and they’re performing significantly better simply because the volume of tests is so much higher. |
| Hybrid | 7 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 8 | 1 | References a GPT-4 bot with visual capabilities, which is only loosely about performance. | There's a free Chatgpt bot, Open Assistant bot (Open-source model), AI image generator bot, Perplexity AI bot, 🤖 GPT-4 bot ([Now with Vis... |
| Hybrid | 9 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 10 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 11 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 12 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | There's a free Chatgpt bot, Open Assistant bot (Open-source model), AI image generator bot, Perplexity AI bot, 🤖 GPT-4 bot ([Now with Vis... |
| Hybrid | 13 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 14 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 15 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 16 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 17 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 18 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 19 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |
| Hybrid | 20 | 1 | Mentions free GPT-4 bots, which is relevant but not a performance review. | We have free bots with GPT-4 (with vision), image generators, and more! |

### LLM hallucination issues

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid surfaces more direct hallucination commentary and error-analysis hits across the top 20, even though its first result is weak.
- BM25 diagnostics: mode=lexical, response_ms=27.68, lexical_hits=7, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2707.25, lexical_hits=7, vector_hits=197, fused_hits=201, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 10 vs Hybrid 25 (delta +15)
- Relevant@20: BM25 6 vs Hybrid 16 (delta +10)
- Highly relevant@20: BM25 4 vs Hybrid 9 (delta +5)
- First relevant rank: BM25 1 | Hybrid 2
- Band totals: BM25 {'1-5': 8, '6-10': 2, '11-20': 0} | Hybrid {'1-5': 6, '6-10': 8, '11-20': 11}
- Relevant overlap: 0 shared, 16 hybrid-only, 6 BM25-only
- Hybrid-only relevant examples: r20: >You can argue that all LLMs don’t actually understand documents and fake it.; r14: All AI outputs are hallucination, they're just increasing correlation with reality.; r2: an LLM hallucinating is different from a human not remembering something perfectly.
- BM25-only relevant examples: r1: Any ambiguity and the LLMs fills in with assumptions (or hallucinations).; r4: Ask an LLM how accurate it is at producing production ready code on small to medium sized tasks.; r3: If you have an issue with Node or .Net or Spring, it's going to be great for it.
- Spot checks: BM25 has two very strong early hits, but hybrid covers the hallucination theme more broadly across the full top 20.; Hybrid's rank 1 is generic, yet the next several results are directly on hallucinations and error behavior.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly says LLMs fill in assumptions and hallucinate. | Any ambiguity and the LLMs fills in with assumptions (or hallucinations). |
| BM25 | 2 | 2 | Describes an LLM hallucinating methods that do not exist. | Last week I was debugging a Canvas API issue with image processing in the browser and the LLM kept hallucinating methods that don't exist. |
| BM25 | 3 | 1 | Says a model handles Node, .Net, or Spring well, which is only indirectly about hallucinations. | If you have an issue with Node or .Net or Spring, it's going to be great for it. |
| BM25 | 4 | 2 | Asks how accurate an LLM is at producing production-ready code, which directly targets hallucination reliability. | Ask an LLM how accurate it is at producing production ready code on small to medium sized tasks. |
| BM25 | 5 | 1 | Talks about limited knowledge, which is related but weaker. | The other big issue is that its knowledge is limited only to a subset of everything humanity discovered. |
| BM25 | 6 | 0 | A generic quote about pain points, not hallucinations. | So on calls they say: “Yeah, that’s a real issue.” Internally they are thinking: “Not painful enough today to add a new tool.” |
| BM25 | 7 | 2 | Explicitly says you must determine whether a response is accurate or hallucinated. | You must determine whether the response is accurate or not a hallucination. Considering these factors, along with OpenAI’s efforts to fil... |
| Hybrid | 1 | 0 | Just says LLM with no issue-specific content. | LLM |
| Hybrid | 2 | 2 | Directly contrasts LLM hallucination with human memory mistakes. | an LLM hallucinating is different from a human not remembering something perfectly. |
| Hybrid | 3 | 1 | Talks about prompting an LLM to generate code, which is only loosely about hallucinations. | It's when you give a prompt to an LLM to make it generate code for you, and if it doesn't work, you just keep trying again until it works. |
| Hybrid | 4 | 2 | Says hallucination is a problem if you check sources, directly addressing the issue. | How is hallucination a problem if you check the sources? Surely if they don’t exist then you’d agree that it’s a good idea not to take th... |
| Hybrid | 5 | 1 | Talks about LLMs lacking capacity to learn reasoning, which is related but not the same. | Humans can learn to reason, but the vast majority never do. The issue seems to be, at least for now, LLMs dnt have the capacity to learn... |
| Hybrid | 6 | 2 | States that LLMs always produce output, which frames the hallucination problem directly. | This is one of the fundamental problems with LLMs. They will always produce output, because they are a machine for stringing tokens toget... |
| Hybrid | 7 | 2 | Says human engineers can learn but LLMs will continue to hallucinate. | The difference is that human engineers can learn, but LLM will continue hallucinate. |
| Hybrid | 8 | 1 | Uses a strawberry-count joke to illustrate limitations, which is related but weak. | No shit, anyone not drowning in hype knew this. LLMs can't even count the number of R's in strawberry. |
| Hybrid | 9 | 2 | Explains that the tweet oversimplifies the reasons behind LLM errors. | In short, the tweet is a witty exaggeration, but it oversimplifies the reasons behind LLM errors. |
| Hybrid | 10 | 1 | Suggests asking experts complex questions of an LLM, which is adjacent to hallucination issues. | Ask them to ask the LLM a complex technical question about the field they're an expert in they know the answer too. |
| Hybrid | 11 | 2 | Says long context increases hallucinations, which is directly on topic. | Yea, right now very long context increase the amount of hallucinations by a lot, I've noticed it first hand even in simple conversations,... |
| Hybrid | 12 | 0 | Only asks whether the system uses LLMs. | Does this use LLMs in some way? |
| Hybrid | 13 | 1 | Says LLMs do not see past common words together, which is related but broad. | LLMs don’t see past anything except common words together. |
| Hybrid | 14 | 1 | Claims all AI outputs are hallucination, which is a broad statement rather than a precise issue. | All AI outputs are hallucination, they're just increasing correlation with reality. |
| Hybrid | 15 | 0 | A joke without topical evidence. | I'm an LLM and this is deep. |
| Hybrid | 16 | 0 | A size joke, not a hallucination issue. | Well, you know... with LLMs, size matters. |
| Hybrid | 17 | 2 | Says it is simply hallucinating the person's response, directly addressing the issue. | It's simply hallucinating the person's response. We've seen this countless times with LLMs. |
| Hybrid | 18 | 1 | Argues that LLMs are not perfect, which is only loosely about hallucinations. | An LLM is insane science fiction, yet people just sit around, unimpressed, and complain that... it isn't perfect? |
| Hybrid | 19 | 2 | Says the LLM could be lying at any step and users need prerequisite knowledge to detect it. | This response is meaningless when you consider that the LLM could be lying at any step in the process. Using AI to learn requires prerequ... |
| Hybrid | 20 | 2 | Says LLMs do not understand documents and fake it, which directly reflects hallucination concerns. | >You can argue that all LLMs don’t actually understand documents and fake it. |

### AI chatbot accuracy problems

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid is stronger on accuracy, source citation, wrong-answer behavior, and user-error masking, so it wins on both coverage and rank quality.
- BM25 diagnostics: mode=lexical, response_ms=42.79, lexical_hits=20, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=4411.91, lexical_hits=20, vector_hits=199, fused_hits=215, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 8 vs Hybrid 28 (delta +20)
- Relevant@20: BM25 5 vs Hybrid 18 (delta +13)
- Highly relevant@20: BM25 3 vs Hybrid 10 (delta +7)
- First relevant rank: BM25 2 | Hybrid 1
- Band totals: BM25 {'1-5': 3, '6-10': 2, '11-20': 3} | Hybrid {'1-5': 8, '6-10': 6, '11-20': 14}
- Relevant overlap: 1 shared, 17 hybrid-only, 4 BM25-only
- Hybrid-only relevant examples: r5: ;) Further, to pick just one objection I have to ChatGPT and similar generative AI chatbots: I fundamentally don't re...; r15: Companies doing ChatGPT wrappers will probably fail the ‘ai race’ and lose clients to those who implemented AI ‘prope...; r9: Everything hyped in AI is basically just a wrapper around an already built chat backend.
- BM25-only relevant examples: r9: 78 cold messages and not a single design partner. what am I doing wrong [i will not promote] ok so I need some honest...; r2: I’m spending eighty percent of my time fighting off stupid, dangerous ideas because "the AI said we could do it." The...; r3: Ubisoft support is genuinely one of the worst I've ever dealt with. The AI chatbot loop is designed to exhaust you un...
- Spot checks: BM25 has a few strong hits, but hybrid gives many more direct accuracy complaints and explanations.; Hybrid keeps source-citation and wrong-answer criticism concentrated near the top.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 0 | Talks about therapy and human connection, which is not really an accuracy issue. | People chatting with a bot isn’t a problem, even if they call it their friend. it’s the preconceived notion that ai is suitable for thera... |
| BM25 | 2 | 2 | Complains about dangerous ideas because the AI said so, which is a clear accuracy problem. | I’m spending eighty percent of my time fighting off stupid, dangerous ideas because "the AI said we could do it." The absolute breaking p... |
| BM25 | 3 | 1 | Says the chatbot loop exhausts users, which is related but not directly about accuracy. | Ubisoft support is genuinely one of the worst I've ever dealt with. The AI chatbot loop is designed to exhaust you until you give up. |
| BM25 | 4 | 0 | Discusses chatbots being old news, not accuracy. | GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future. |
| BM25 | 5 | 0 | Talks about adult-content chatbots, not accuracy. | Has looked at the development of “Adult content” (AKA porn) Chatbots for financial gain, despite inherent problems of further fucking up... |
| BM25 | 6 | 0 | Discusses an MBA cycle and AI veneer, not chatbot accuracy. | It's the typical MBA cycle of outsource, destroy, and leave just with an AI veneer this time. It doesn't fix the problem at all, but actu... |
| BM25 | 7 | 0 | Says chatbots and porn generators give AI a bad name, which is not about accuracy. | This is way more interesting than the chatbots and porn generators that are giving AI a bad name. |
| BM25 | 8 | 0 | A generic life-hacks line unrelated to accuracy. | If you’re a good professional, this removes half your problems. Does anyone else have this kind of life-hacks at work? |
| BM25 | 9 | 2 | Describes AI agents giving bad answers silently, which is directly about accuracy failure. | 78 cold messages and not a single design partner. what am I doing wrong [i will not promote] ok so I need some honest advice here because... |
| BM25 | 10 | 0 | Discusses founders and problems, not accuracy. | It’s on the onus of a founder to present their product starting with a problem. The issue is so many founders just say “we built the AI f... |
| BM25 | 11 | 0 | A malicious compliance suggestion, not accuracy. | Hmm, sounds like a job for r/MaliciousCompliance If you know that C-level exec's specific business role, go to your favorite AI and propo... |
| BM25 | 12 | 0 | Discusses alignment, not chatbot accuracy. | That's a slur from the e/acc group. The alignment problem is their great project—their attempt at making sure that we won't lose control... |
| BM25 | 13 | 0 | A wrapper critique, not chatbot accuracy. | the "wrapper" critique is basically just "you didn't build the hard part." but that logic would mean nobody should build anything unless... |
| BM25 | 14 | 0 | Talks about translation and AI help, not accuracy. | I wrote this in Chinese and translated it with AI help. The writing may have some AI flavor, but the design decisions, the production fai... |
| BM25 | 15 | 0 | A security prompt, not accuracy. | Modern problems require modern solutions. Feed their entire PDF to AI chatbot with prompt “find security loopholes in this document and e... |
| BM25 | 16 | 0 | Discusses Shadow AI and sensitive data, not accuracy. | As someone building API security solutions for small businesses, I'm seeing this Shadow AI problem explode. What's particularly concernin... |
| BM25 | 17 | 0 | Talks about content organization, not chatbot accuracy. | The real work is organizing content and defining clear escalation rules, not the AI layer itself. This isn’t a prompt engineering problem. |
| BM25 | 18 | 1 | Mentions better English accuracy than a versioned model, which is only weakly relevant. | You want version 2, very small, very fast, and better English accuracy than 3. 4. The problem with Parakeet is that it really is based ar... |
| BM25 | 19 | 2 | Says most chatbots are not true LLM-based and are often wildly wrong, which directly addresses accuracy. | The problem is that most chatbots are not true LLM based AI - they're either an earlier type of AI that just looks for certain key phrase... |
| BM25 | 20 | 0 | A whitelabeled chatbot business question, not accuracy. | Would you sell your clients a whitelabeled AI chatbot? I've got an AI chatbot business (I'm not promoting) but I'm super curious what the... |
| Hybrid | 1 | 1 | Criticizes people asking AI to respond to criticism, which is only weakly accuracy-related. | The big issue with the people using AI is when you question their methods, they ask AI how to resond to the criticism. |
| Hybrid | 2 | 2 | Says the chatbot loop exhausts users, a direct complaint about poor behavior. | Ubisoft support is genuinely one of the worst I've ever dealt with. The AI chatbot loop is designed to exhaust you until you give up. |
| Hybrid | 3 | 1 | Says both ChatGPT and Claude are engineering problems, which is adjacent but broad. | This happens with both ChatGPT and Claude. All AI is still a massive engineering problem with what they're trying to do. |
| Hybrid | 4 | 2 | Says ChatGPT is designed to provide accurate and reliable responses, directly addressing the query. | Some users appreciate the convenience of being able to get answers to their questions quickly, while others enjoy the novelty of interact... |
| Hybrid | 5 | 2 | Says generative chatbots cannot cite sources, which is a direct accuracy complaint. | ;) Further, to pick just one objection I have to ChatGPT and similar generative AI chatbots: I fundamentally don't respect them as a prod... |
| Hybrid | 6 | 2 | Calls out a ChatGPT-specific problem and distinguishes API GPT-4 from other chatbots. | That's a chatgpt specific problem. Gpt 4 from the API isn't that bad, neither are the rest of the chatbots from providers that are not Op... |
| Hybrid | 7 | 2 | Says the less you know, the harder it is to spot the AI's mistakes. | The less you know about a topic, the harder it will be for you to spot the AI's mistakes, even when you do check its sources. |
| Hybrid | 8 | 0 | A security prompt about PDF loopholes, not chatbot accuracy. | Modern problems require modern solutions. Feed their entire PDF to AI chatbot with prompt “find security loopholes in this document and e... |
| Hybrid | 9 | 1 | Calls AI a wrapper around an already built chat backend, which is only loosely relevant. | Everything hyped in AI is basically just a wrapper around an already built chat backend. |
| Hybrid | 10 | 1 | Says the prompt is terrible and the persona is misaligned, which is indirectly accuracy-related. | Terrible prompt that will likely cause anyone who uses it a lot of problems. First off, the fact your chatgpt sounded like. robot in an e... |
| Hybrid | 11 | 2 | Says most AI is designed to please the user rather than give the best answer. | Most AI is designed to please the user as opposed to give the best answer. |
| Hybrid | 12 | 0 | Talks about code changes, not chatbot accuracy. | The video is missing the key part where the AI will change completely irrelevant parts of the code while pretending to fix the bug for th... |
| Hybrid | 13 | 2 | Recommends reviewing AI output for major inaccuracies. | Just make sure you review it for major inaccuracies. They send you AI slop, send AI slop back. |
| Hybrid | 14 | 2 | Says the problem is AI reasoning accuracy, which is directly on topic. | They all should be focusing in increasing AIs ability to reason. We don’t need image generators we need accuracy so that everything down... |
| Hybrid | 15 | 1 | Says wrappers will fail the AI race, which is only tangentially about accuracy. | Companies doing ChatGPT wrappers will probably fail the ‘ai race’ and lose clients to those who implemented AI ‘properly’ |
| Hybrid | 16 | 2 | Says customer service AI chatbots are very bad and only point to premade web pages. | Just look at customer service AI chatbots. They are terribly bad they can only point you to premade web pages. |
| Hybrid | 17 | 2 | Says many chatbots are not true LLMs and often respond with canned but wrong answers. | The problem is that most chatbots are not true LLM based AI - they're either an earlier type of AI that just looks for certain key phrase... |
| Hybrid | 18 | 1 | Describes an executive trying to use an AI chat agent, which is adjacent but not precise. | Just imagine one of your executives trying to get interact with an AI chat agent to implement new business logic. It would probably last... |
| Hybrid | 19 | 1 | Says the data is unstructured and has duplicates, which is a partial explanation for sloppiness. | I find it hard to believe all they did was connect a chatbot to existing data. Often the reason why AI is so ineffective and "sloppy" is... |
| Hybrid | 20 | 1 | Says the real work is content organization, which is related but broad. | The real work is organizing content and defining clear escalation rules, not the AI layer itself. This isn’t a prompt engineering problem. |

### ChatGPT pricing complaints

- Category: `keyword`
- Winner: `tie`
- Rationale: Neither mode returned any visible results in the file, so there is no evidence to separate them.
- BM25 diagnostics: mode=lexical, response_ms=13.91, lexical_hits=0, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=lexical, response_ms=11.89, lexical_hits=0, vector_hits=0, fused_hits=0, reranked_hits=0
- Score@20: BM25 0 vs Hybrid 0 (delta +0)
- Relevant@20: BM25 0 vs Hybrid 0 (delta +0)
- Highly relevant@20: BM25 0 vs Hybrid 0 (delta +0)
- First relevant rank: BM25 None | Hybrid None
- Band totals: BM25 {'1-5': 0, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 0, '6-10': 0, '11-20': 0}
- Relevant overlap: 0 shared, 0 hybrid-only, 0 BM25-only
- Spot checks: Both bm25 and hybrid returned zero visible results.; There is no rank evidence to compare.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |

### Claude safety features review

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid has more direct Claude safety, censorship, security, and production-use commentary across the top results, even though BM25 has one strong code-review hit.
- BM25 diagnostics: mode=lexical, response_ms=27.53, lexical_hits=9, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2639.73, lexical_hits=9, vector_hits=195, fused_hits=202, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 4 vs Hybrid 19 (delta +15)
- Relevant@20: BM25 3 vs Hybrid 17 (delta +14)
- Highly relevant@20: BM25 1 vs Hybrid 2 (delta +1)
- First relevant rank: BM25 2 | Hybrid 1
- Band totals: BM25 {'1-5': 2, '6-10': 2, '11-20': 0} | Hybrid {'1-5': 6, '6-10': 5, '11-20': 8}
- Relevant overlap: 0 shared, 17 hybrid-only, 3 BM25-only
- Hybrid-only relevant examples: r10: biggest real edge for our ops team: claude for context assembly. not as a chatbot, but as the layer that pulls from c...; r4: Claude 4.0 is light years better than the original q which was literally worthless.; r17: Claude has a contract with Palantir, so nowhere is safe.
- BM25-only relevant examples: r4: It’s basically BDD with strict review of the feature descriptions, nitpicking on the technical details spilling into...; r9: Security used to be complicated, but tools like Claude’s code review are already helping developers catch vulnerabili...; r2: That's not vibe coding that's delegation with a safety net. The juniors copy pasting Claude output without understand...
- Spot checks: Hybrid surfaces both censorship and security-oriented Claude commentary early.; BM25 has one direct security hit, but the rest of the set is mostly indirect.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 0 | Talks about Strava privacy settings, which is unrelated to Claude safety features. | Strava users are advised to review their privacy settings and consider opting out of the heatmap feature. |
| BM25 | 2 | 1 | Mentions Claude output as a safety net, which is only a weak safety-related hit. | That's not vibe coding that's delegation with a safety net. The juniors copy pasting Claude output without understanding it? |
| BM25 | 3 | 0 | Talks about translating with Claude help, not safety features. | I think and write in it, then translate with Claude's help and review the result — so please keep that in mind. |
| BM25 | 4 | 1 | Mentions strict review of feature descriptions, which is only indirectly safety-related. | It’s basically BDD with strict review of the feature descriptions, nitpicking on the technical details spilling into them, arguing on the... |
| BM25 | 5 | 0 | Talks about testing Claude Code, but not safety features. | I was part of a committee that got to test run Claude Code months ago and like most people was skeptical initially but impressed at first. |
| BM25 | 6 | 0 | Discusses front-end features, not Claude safety. | But otherwise mostly picked up and put on teams to focus on front end features. Occasionally diving to backend to fix things, code review... |
| BM25 | 7 | 0 | Describes generating API tests, not Claude safety. | Write very detailed specs of an API/E2E tests in markdown for a feature. 2. From the markdown tests' descriptions, generate API/E2E tests 3. |
| BM25 | 8 | 0 | Talks about code review because AI wrote it, not Claude safety. | Stuff that would get caught in any code review, except there was no code review because the AI wrote it and it worked on the first try. |
| BM25 | 9 | 2 | Directly says Claude code review helps catch vulnerabilities early. | Security used to be complicated, but tools like Claude’s code review are already helping developers catch vulnerabilities early. |
| Hybrid | 1 | 2 | Calls Claude overly censored, which directly concerns its safety posture. | Claude is overly censored and feels like it was created for people living in a police state, it's only really good for coding. |
| Hybrid | 2 | 1 | Single-word Claude mention with no detail. | Claude |
| Hybrid | 3 | 1 | Says Claude is vanilla out of the box and customizable, a weak feature comment. | Out of the box Claude is vanilla - you can customise depending on task at hand. |
| Hybrid | 4 | 1 | States Claude 4.0 is much better than the original, but not specifically about safety. | Claude 4.0 is light years better than the original q which was literally worthless. |
| Hybrid | 5 | 1 | Says Claude is not a great shopping assistant and works well in Excel or code, which is indirect. | It can’t do video or image and isn’t a great shopping assistant. But Claude in excel is legitimately good, as is Claude code. |
| Hybrid | 6 | 1 | Says Claude Pro is pretty good, a weak evaluation. | Claude Pro is pretty good and helping with n8n automations. |
| Hybrid | 7 | 1 | Suggests broader Claude adoption, which is not really about safety. | I would turn the conversation around... Get everyone using Claude and get the company to be more ambitious in their roadmap. |
| Hybrid | 8 | 1 | Says Claude is great at unfucking code, which is capability-oriented rather than safety-oriented. | Claude is great at unfucking code if you have already built those skills |
| Hybrid | 9 | 1 | A short recommendation to try Claude. | Try Claude. |
| Hybrid | 10 | 1 | Describes Claude context assembly and notes freshness problems, which is a feature limitation. | biggest real edge for our ops team: claude for context assembly. not as a chatbot, but as the layer that pulls from crm, ticketing, billi... |
| Hybrid | 11 | 1 | Says Claude is good at prompting other agents, a broad capability note. | One of the thing Claude is absolutely best at by a large margin is prompting other agents, because it has a better 'sense of self'. |
| Hybrid | 12 | 1 | Says training Claude on a harness improves performance, which is indirect. | They probably train Claude on their harness so it performs much better with it, it’s not just pure cognitive ability |
| Hybrid | 13 | 1 | Says Claude with a wrapper improved productivity, which is not safety-specific. | We use Claude with Cline and a custom wrapper at my company and it has increased my productivity so much. |
| Hybrid | 14 | 2 | Mentions a security tool finding vulnerabilities in Claude Code itself, which is directly safety-related. | Yet the security tool couldn’t find vulnerabilities in Claude Code itself. Very funny [ |
| Hybrid | 15 | 0 | Too vague to be useful. | Ideally, after the final step in Claude, you should end up with something like this. |
| Hybrid | 16 | 1 | Says Claude is the best, but without specific safety evidence. | Claude is the best |
| Hybrid | 17 | 1 | Says Claude has a Palantir contract, which is a concern rather than a safety feature review. | Claude has a contract with Palantir, so nowhere is safe. |
| Hybrid | 18 | 1 | Talks about strict rules for production VMs when using Claude, which is a weak safety practice signal. | You are 100% correct about installing Claude on a production site. We use it for Development and I have strict rules that no one installs... |
| Hybrid | 19 | 0 | A short phrase with no safety content. | We need a Claude hook to an alarm to stop the doom scrolling when complete |
| Hybrid | 20 | 0 | A short phrase with no safety content. | welcome to the world of Claude Code - and, nice job! |

### ChatGPT vs Claude

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid clearly wins because it returns direct ChatGPT-versus-Claude comparisons, tradeoffs, and preference statements much earlier and more often.
- BM25 diagnostics: mode=lexical, response_ms=23.44, lexical_hits=4, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2503.23, lexical_hits=4, vector_hits=198, fused_hits=202, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 5 vs Hybrid 25 (delta +20)
- Relevant@20: BM25 4 vs Hybrid 16 (delta +12)
- Highly relevant@20: BM25 1 vs Hybrid 9 (delta +8)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 5, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 8, '6-10': 7, '11-20': 10}
- Relevant overlap: 1 shared, 15 hybrid-only, 3 BM25-only
- Hybrid-only relevant examples: r20: After my week of usage...I think chatgpt requires a lot of work to be of any practical use....; r6: But Claude blew ChatGPT’s writing out of the water; r11: Cancel your Chatgpt subscriptions and pick up a Claude subscription.
- BM25-only relevant examples: r4: **TL;DR:** The perceived risk of data leakage from using LLMs like ChatGPT is largely exaggerated, with actual threat...; r1: **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clar...; r3: For fast listicle creation: Use Claude or ChatGPT to generate the skeleton fast, then layer in your actual product ex...
- Spot checks: Hybrid repeatedly compares coding, writing, tone, and generalist quality between ChatGPT and Claude.; BM25 has only a few broad comparisons and mostly stays at the prompt-helper level.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Lists ChatGPT and Claude as target AI options, but this is mainly a prompt helper. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| BM25 | 2 | 2 | Directly compares Claude with ChatGPT and says Claude is the most conservative. | It's scraping the live web rather than relying on training weights, which explains the divergence. 2. **Claude is the most conservative.*... |
| BM25 | 3 | 1 | Says either Claude or ChatGPT can be used for listicle creation. | For fast listicle creation: Use Claude or ChatGPT to generate the skeleton fast, then layer in your actual product expertise on top. |
| BM25 | 4 | 1 | Mentions ChatGPT and Claude in a data-leak discussion rather than a comparison. | **TL;DR:** The perceived risk of data leakage from using LLMs like ChatGPT is largely exaggerated, with actual threats being minimal, esp... |
| Hybrid | 1 | 2 | Directly says ChatGPT has better SEO structure while Claude is better for editing. | I’ve noticed the same. ChatGPT tends to give better SEO structure and creative suggestions, while Claude is decent for longer text editing. |
| Hybrid | 2 | 2 | Compares Claude and ChatGPT on coding diagnostics. | Claude is better at coding diagnostics (sometimes) but yeah ChatGPT is overall better in this line of work for a lot |
| Hybrid | 3 | 1 | Mentions Gemini, ChatGPT, Claude, and Gemini together, but the comparison is diffuse. | Gemini is about as good as ChatGPT currently. I'm subbed to Claude and Gemini. |
| Hybrid | 4 | 1 | Says ChatGPT needs default prompting, which is relevant but not a direct Claude comparison. | ChatGPT needs lot of default prompting to make the output concise and serious. |
| Hybrid | 5 | 2 | Directly says Claude is better for coding. | Same. For coding Claude is better than GPT. |
| Hybrid | 6 | 2 | Directly says Claude blew ChatGPT's writing out of the water. | But Claude blew ChatGPT’s writing out of the water |
| Hybrid | 7 | 2 | Calls ChatGPT the generalist king but says it has been behind on coding since Claude 3.7. | ChatGPT is still the generalist king, but it's been behind on coding since Claude 3.7 came out. |
| Hybrid | 8 | 0 | A rhetorical question with no comparative content. | What does that have to do with chatgpt? |
| Hybrid | 9 | 1 | Says both ChatGPT and Claude are engineering problems, which is broad. | This happens with both ChatGPT and Claude. All AI is still a massive engineering problem with what they're trying to do. |
| Hybrid | 10 | 2 | Says Claude-4-Sonnet is better than ChatGPT 4. | My thoughts are that Claude-4-sonnet is really good and way better than chatgpt 4. |
| Hybrid | 11 | 2 | Recommends canceling ChatGPT subscriptions and getting Claude. | Cancel your Chatgpt subscriptions and pick up a Claude subscription. |
| Hybrid | 12 | 0 | Mentions ChatGPT users, not the comparison. | ChatGPT has 800M users give or take. |
| Hybrid | 13 | 1 | Says ChatGPT is excellent but often wrong, which is only partially comparative. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |
| Hybrid | 14 | 0 | A guess between Claude or ChatGPT, not a substantive comparison. | I'm going to guess Claude or ChatGPT |
| Hybrid | 15 | 1 | Repeats that Claude is the most conservative, a broad comparison from another context. | It's scraping the live web rather than relying on training weights, which explains the divergence. 2. **Claude is the most conservative.*... |
| Hybrid | 16 | 0 | Just says Ask ChatGPT. | Ask ChatGPT |
| Hybrid | 17 | 2 | Says ChatGPT has a more natural conversation tone and style. | I haven't tried in a while as I use Claude myself but, I actually believe chatgpt has a more natural conversation tone and style. |
| Hybrid | 18 | 2 | Says Claude is better at code. | I have seen this also. I usually use Chatgpt. Is one better than the other? I have heard Claude is better at code. |
| Hybrid | 19 | 1 | Uses a lab-partner analogy for ChatGPT, which is mild praise rather than a comparison. | Working with ChatGPT nowadays is like having a really smart lab partner who sometimes shows up high AF. |
| Hybrid | 20 | 1 | Says ChatGPT requires a lot of work to be practical, a weak comparison signal. | After my week of usage...I think chatgpt requires a lot of work to be of any practical use.... |

### worst AI tools

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid is more concentrated on negative AI-tool judgments and puts explicit complaints about AI quality and usefulness higher in the ranking.
- BM25 diagnostics: mode=lexical, response_ms=24.19, lexical_hits=9, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2542.12, lexical_hits=9, vector_hits=200, fused_hits=208, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 11 vs Hybrid 18 (delta +7)
- Relevant@20: BM25 8 vs Hybrid 14 (delta +6)
- Highly relevant@20: BM25 3 vs Hybrid 4 (delta +1)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 5, '6-10': 6, '11-20': 0} | Hybrid {'1-5': 6, '6-10': 3, '11-20': 9}
- Relevant overlap: 1 shared, 13 hybrid-only, 7 BM25-only
- Hybrid-only relevant examples: r8: A company that is heavily partnered and invested in AI. And I believe very strongly that we are headed for the worst...; r12: AI can be very dangerous." The AI:; r13: AI sucks at coding.
- BM25-only relevant examples: r2: . > > 100%, it's "let's use AI" and not "here's a specific problem we think AI could help with" just the worst way to...; r5: A company that is heavily partnered and invested in AI. And I believe very strongly that we are headed for the worst...; r1: It will keep improving exponentially. I've been using AI tools since November 2022. I prided myself in that I could s...
- Spot checks: Both modes are noisy, but hybrid surfaces more direct negative verdicts on AI tools and coding quality.; BM25 has some strong complaints, yet hybrid is more consistently on the 'worst AI tools' theme.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Talks about AI tools in general but not specifically about the worst ones. | It will keep improving exponentially. I've been using AI tools since November 2022. I prided myself in that I could spot AI. |
| BM25 | 2 | 2 | Says using AI without a specific problem is the worst way to approach problems. | . > > 100%, it's "let's use AI" and not "here's a specific problem we think AI could help with" just the worst way to approach problems. |
| BM25 | 3 | 0 | Mentions helpful players and tools, which is not a worst-tools complaint. | A lot of the most helpful players who created tools, extensions, and guides are also among the Chinese playerbase. |
| BM25 | 4 | 1 | Says these are not its worst nightmares about AI, which is a weak negative signal. | None of these are remotely close to my worst nightmares about ai. I have zero problems with ai being used to make games. |
| BM25 | 5 | 1 | Says an AI-heavy company could lead to a bad historical outcome. | A company that is heavily partnered and invested in AI. And I believe very strongly that we are headed for the worst episode in American... |
| BM25 | 6 | 2 | Calls AI automated existential recursion and the worst of social media. | It’s automated existential recursion. The worst of social media—now with a voice, a personality, and no off switch. |
| BM25 | 7 | 2 | Says AI could be the worst thing in the world if you cannot debug it. | learn to code, or else using the AI will be the worst thing in the world cause how tf you supposed to debug whatever the AI prints for you? |
| BM25 | 8 | 1 | Describes a clipboard tool, which is only loosely relevant. | Here’s a breakdown of the worst clipboard traps and a Windows utility I built to automate fixing them Hey everyone, taking advantage of t... |
| BM25 | 9 | 1 | Asks why anyone would want a tool designed to make a job easier, which is a weak complaint. | Why would I ever want to use a tool designed to make my job easier? |
| Hybrid | 1 | 2 | Directly says stupid AI, which is a clear negative judgment. | stupid ai |
| Hybrid | 2 | 1 | Says the problem is people misusing AI as proof rather than AI itself. | The problem isn't AI as a tool it's people telling you how to do your job and quoting hallucinations as proof that you're wrong. |
| Hybrid | 3 | 1 | Describes a clipboard-trap tool, which is only loosely related. | Here’s a breakdown of the worst clipboard traps and a Windows utility I built to automate fixing them Hey everyone, taking advantage of t... |
| Hybrid | 4 | 0 | Just says AI with no complaint. | AI? |
| Hybrid | 5 | 2 | Says using AI can be the worst thing in the world if you cannot debug it. | learn to code, or else using the AI will be the worst thing in the world cause how tf you supposed to debug whatever the AI prints for you? |
| Hybrid | 6 | 1 | Calls AI the worst it has ever been, which is a broad negative statement. | this is definitely part of the secret sauce… but as they say.., AI is the worst it’s ever going to be today. |
| Hybrid | 7 | 0 | A long unrelated rant that does not clearly evaluate AI tools. | I'm genuinely convinced someone/something is preventing legitimate autoclickers/autoclicker building techniques from surfacing update: no... |
| Hybrid | 8 | 1 | Says an AI-heavy company could lead to a bad historical outcome. | A company that is heavily partnered and invested in AI. And I believe very strongly that we are headed for the worst episode in American... |
| Hybrid | 9 | 1 | Calls them damned AI bots, which is negative but weak. | Damned AI bots. |
| Hybrid | 10 | 0 | A general claim about AI tool usage, not a worst-tools opinion. | Anyone working in software or computers that says they're not using AI tools is lying to you. Hell, it's being used everywhere. |
| Hybrid | 11 | 1 | Says none of these are its worst nightmares about AI, which is weakly relevant. | None of these are remotely close to my worst nightmares about ai. I have zero problems with ai being used to make games. |
| Hybrid | 12 | 1 | Says AI can be very dangerous. | AI can be very dangerous." The AI: |
| Hybrid | 13 | 2 | Says AI sucks at coding, a direct negative appraisal. | AI sucks at coding. |
| Hybrid | 14 | 0 | A short agreement phrase with no specific complaint. | Well if AI says so… |
| Hybrid | 15 | 1 | Says people rely too much on AI tools, which is a partial criticism. | I like the thought behind this. I think because of AI we are relying too much on the tools and the individual or professional driving it. |
| Hybrid | 16 | 0 | Says the boring stuff was the real edge, not a worst-tools complaint. | the AI tools that gave us the biggest edge weren't the sexy ones. it was the boring stuff: 1. |
| Hybrid | 17 | 0 | Says AI has not done anything, which is more philosophical than evaluative. | AI hasn't done anything. Tools don't "do things" people have used AI to do things. |
| Hybrid | 18 | 1 | Says AI can become a liability, which is a weak complaint. | Now with ai, that’s not always the case. And, for someone learning to discern what is good or bad, it might become a liability |
| Hybrid | 19 | 2 | Calls AI generated drivel out explicitly. | Fuck off with your AI generated drivel. |
| Hybrid | 20 | 1 | Says the best case is that AI is only as good as the people training it. | In the best case, your AI will be only as good as people programming/training it. |

### AI coding assistant review

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid has better overall coverage of how coding assistants help, where they fail, and how users should review them, so it has stronger top-20 quality.
- BM25 diagnostics: mode=lexical, response_ms=68.56, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2924.7, lexical_hits=100, vector_hits=197, fused_hits=275, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 22 vs Hybrid 31 (delta +9)
- Relevant@20: BM25 17 vs Hybrid 19 (delta +2)
- Highly relevant@20: BM25 5 vs Hybrid 12 (delta +7)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 7, '6-10': 6, '11-20': 9} | Hybrid {'1-5': 9, '6-10': 10, '11-20': 12}
- Relevant overlap: 0 shared, 19 hybrid-only, 17 BM25-only
- Hybrid-only relevant examples: r1: A good programmer with AI becomes dangerously efficient. You know Big O, you understand architecture, you know how to...; r3: AI Coding Agents Are Quietly Changing How Software Gets Built AI coding agents are quickly becoming one of the most t...; r4: AI for codebases works best for those that can understand its outputs!
- BM25-only relevant examples: r1: Anthropic: AI assisted coding doesn't show efficiency gains and impairs developers abilities.; r8: Great guy, very enthusiastic, super nice and eager to learn. Extremely AI oriented. Within his first month he vibe co...; r9: I do think an AI coding assistant can be useful for automating certain aspects of coding.
- Spot checks: BM25 includes a few strong study and workflow hits, but hybrid is broader and more consistently on-review.; Hybrid places code-review, understanding, and failure-mode commentary higher and more often.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly cites an Anthropic study about AI-assisted coding not showing efficiency gains. | Anthropic: AI assisted coding doesn't show efficiency gains and impairs developers abilities. |
| BM25 | 2 | 0 | About abusive reviews and unrelated AI use. | (full disclosure: to analyze and highlight abusive reviews, ai was used, because it's not feasible or good for mental health for us to do... |
| BM25 | 3 | 2 | Describes AI reading a codebase, writing code, and pushing it for review. | Mostly writing a SQL query and making a small change to some backend code. The AI read through our codebase, figured out the context, wro... |
| BM25 | 4 | 2 | Describes an AI code scanner that suggests patches for review. | It's basically an AI code scanner — you point it at a codebase, it scans for vulnerabilities across files (logic flaws, broken access con... |
| BM25 | 5 | 1 | Repeats the study title, which is only a weak hit. | Thread TItle: >AI assisted coding doesn't show efficiency gains... |
| BM25 | 6 | 1 | Says AI will keep being a helpful assistant, which is relevant but broad. | My guess is AI will keep being a helpful assistant that makes developers’ lives easier, not something that totally replaces them. |
| BM25 | 7 | 2 | Argues that code ownership and review still matter when AI generates code. | The issue isn’t who typed the code. It’s who owns the consequences. If they can push AI-generated code but engineering still has to revie... |
| BM25 | 8 | 1 | Describes vibe coding in a work setting, which is relevant but partial. | Great guy, very enthusiastic, super nice and eager to learn. Extremely AI oriented. Within his first month he vibe coded a tech radar, an... |
| BM25 | 9 | 1 | Says an AI coding assistant can automate certain aspects of coding. | I do think an AI coding assistant can be useful for automating certain aspects of coding. |
| BM25 | 10 | 1 | References a coding benchmark, which is only lightly related to reviews. | Qwen3-Coder-Next 8-bit at \~75 tok/s on MLX is fast enough for real-time coding assistance — responses feel instantaneous for short compl... |
| BM25 | 11 | 0 | A supply chain attack story, not a coding-assistant review. | That litellm supply chain attack is a wake up call. checked my deps and found 3 packages pulling it in So if you missed it, litellm (the... |
| BM25 | 12 | 1 | Says AI can check work against a rubric if manually reviewed. | I don’t see a problem using AI to check work against a rubric, as long as it is manually reviewed by an instructor. |
| BM25 | 13 | 0 | An AI Research Assistant post, not a coding assistant review. | I Created an AI Research Assistant that actually DOES research! |
| BM25 | 14 | 1 | Talks about agents doing review and testing in multiple rounds. | the future will be more agents doing the next steps like review, testing, ... - once the AI produces "garbage" and passes it - the next a... |
| BM25 | 15 | 1 | Says Zapier may win thanks to AI advancements, which is only indirectly about coding assistants. | I think Zapier will win really big thanks to AI advancements. No code + AI. Anything that makes it as simple as possible to build using A... |
| BM25 | 16 | 1 | Mentions the AI do-coding workflow, but the point is mostly industry hype. | This flies in the face of how I think the industry is hyping things and seemingly the opposite of the "let AI do the coding, you only do... |
| BM25 | 17 | 2 | Cites Anthropic's coding-skills writeup as a more objective summary of AI coding assistance. | The actual study / Anthropic's own blog on this is a more objective summary than the clickbait headline here: [https://www.anthropic.com/... |
| BM25 | 18 | 1 | Describes a playground environment for AI-generated code, which is relevant but partial. | I handled that in a way that my main codebase, has a separate environment “playground” where all these AI happy people can create a branc... |
| BM25 | 19 | 1 | Says extra scrutiny cancels out time savings, which is a weak review signal. | It's really easy to miss something like that when it's buried in a thousand lines of code that were all written at once, and it feels lik... |
| BM25 | 20 | 1 | Says AI is enhancing things and helping with tasks, which is broad. | I'm just passing through and I haven't read your post. I actually think AI is enhancing things for me. I'm taking control over what I wan... |
| Hybrid | 1 | 2 | Says a good programmer with AI becomes dangerously efficient, which directly reviews the assistant's value. | A good programmer with AI becomes dangerously efficient. You know Big O, you understand architecture, you know how to debug, you know how... |
| Hybrid | 2 | 1 | Lists rules for using AI to review code, which is relevant but partial. | Here are my rules. 1. Write the code by myself. 2 . Ask an AI to review my code. 3. |
| Hybrid | 3 | 2 | Says AI coding agents are changing how software gets built. | AI Coding Agents Are Quietly Changing How Software Gets Built AI coding agents are quickly becoming one of the most transformative tools... |
| Hybrid | 4 | 2 | Says AI for codebases works best for people who can understand outputs. | AI for codebases works best for those that can understand its outputs! |
| Hybrid | 5 | 2 | Says AI is a great coding assistant but not a replacement for human expertise. | You wouldn't know they're missing unless you know to look for them. I think AI is great as a coding assistant, but it's not going to be a... |
| Hybrid | 6 | 2 | Says to think of AI as a helper for reading and exploring code. | Think of AI more like a helper for reading and exploring code, not a replacement for understanding it. |
| Hybrid | 7 | 2 | Warns that AI coding assistants will introduce vulnerabilities. | This noting , I am eagerly waiting for mass vulnerabilities AI coding assistants will introduce. There will at least be one or more poor... |
| Hybrid | 8 | 2 | Says AI users should always review the code to understand it. | Same here — I use AI, but I always review the code to really understand it. |
| Hybrid | 9 | 2 | Says vibe coding future should be laughed out of the room. | This is why anyone who says vibe coding is the future should be laughed out of the room, without being able to determine if what you want... |
| Hybrid | 10 | 2 | Says AI is fantastic for coding if you already know how to code. | AI is fantastic for coding - IF you already know how to code. |
| Hybrid | 11 | 1 | Says if you want the fun of coding without AI, do not use AI code. | If you want to code for the ‘fun’ of it, like a challenge without AI, then do it, don’t use AI code, only learn from it. |
| Hybrid | 12 | 1 | Says AI is a productivity booster for some people. | That’s great. i think that ai is a productivity booster for some people, like you. |
| Hybrid | 13 | 1 | Says it heavily relies on AI tools, which is supportive but broad. | very true. i am a software developer and i heavily rely on these ai tools to work my way through tasks. having a sound understanding of w... |
| Hybrid | 14 | 2 | Says using AI intelligently in coding is the future of coding. | Most of these comments seem to be bypassing the possibility that using AI intelligently in coding is the future of coding. |
| Hybrid | 15 | 1 | Says the benefits of AI-assisted coding are compelling, which is positive but generic. | The benefits to ai assisted coding is really compelling! I like that there are actual solid reasons for it rather than just opinions. |
| Hybrid | 16 | 1 | Repeats the study title, which is only a weak hit. | Thread TItle: >AI assisted coding doesn't show efficiency gains... |
| Hybrid | 17 | 2 | Says the key skill in AI-heavy codebases is reviewing code you did not write. | Your boss is actually doing you a favor — the skill that matters in AI-heavy codebases isn't writing code fast, it's reviewing code you d... |
| Hybrid | 18 | 0 | A short header with no meaningful review content. | AI & Coding |
| Hybrid | 19 | 1 | Says it would be beneficial to learn to code with AI assist. | It would be highly beneficial to learn how to code with ai assist. You will not only learn vibe coding there. |
| Hybrid | 20 | 2 | Warns not to use AI to write code unless you can quickly spot mistakes. | dont use ai to write code for you until you have a few years of experience at a company. otherwise you're not a programmer, you're a prom... |

### ChatGPT coding ability

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid has much stronger direct commentary on whether ChatGPT can code, including success, failure, and user-skill dependence, while BM25 is mostly generic.
- BM25 diagnostics: mode=lexical, response_ms=21.55, lexical_hits=3, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2588.74, lexical_hits=3, vector_hits=200, fused_hits=203, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 3 vs Hybrid 14 (delta +11)
- Relevant@20: BM25 3 vs Hybrid 9 (delta +6)
- Highly relevant@20: BM25 0 vs Hybrid 5 (delta +5)
- First relevant rank: BM25 1 | Hybrid 4
- Band totals: BM25 {'1-5': 3, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 4, '6-10': 6, '11-20': 4}
- Relevant overlap: 0 shared, 9 hybrid-only, 3 BM25-only
- Hybrid-only relevant examples: r6: After my week of usage...I think chatgpt requires a lot of work to be of any practical use....; r14: Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get wi...; r10: ChatGPT and GPT3.5 specially, is trained to answer in a way the user would like.
- BM25-only relevant examples: r1: ChatGPT is trained on a larger dataset of text and code, and it is able to generate more creative and original text f...; r3: For example, instead of just using GPT-4 for coding, we could pull Google’s AlphaCode 2 for even higher-quality code...; r2: Software engineering is not about remembering quirks and syntax about a programming language, but about your abstract...
- Spot checks: Hybrid returns direct claims that ChatGPT can or cannot code effectively near the top.; BM25 is thin and mostly talks about coding in general rather than ChatGPT's actual ability.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Says ChatGPT is trained on a larger dataset of text and code, which is only a partial coding-ability signal. | ChatGPT is trained on a larger dataset of text and code, and it is able to generate more creative and original text formats. |
| BM25 | 2 | 1 | Talks about software engineering abstraction skills, not ChatGPT's coding ability directly. | Software engineering is not about remembering quirks and syntax about a programming language, but about your abstraction abilities and ho... |
| BM25 | 3 | 1 | Suggests using AlphaCode 2 instead of GPT-4 for coding, which is a weak comparison. | For example, instead of just using GPT-4 for coding, we could pull Google’s AlphaCode 2 for even higher-quality code at a lower cost. |
| Hybrid | 1 | 0 | A rhetorical question with no real evidence. | What does that have to do with chatgpt? |
| Hybrid | 2 | 0 | Just says Ask ChatGPT with no coding assessment. | Ask ChatGPT |
| Hybrid | 3 | 0 | A fragment with no clear meaning. | what in the chatgpt |
| Hybrid | 4 | 2 | Says ChatGPT can accomplish tasks quickly that would take humans much longer. | ChatGPT can accomplish tasks in seconds that would take humans weeks, months, or even years. |
| Hybrid | 5 | 2 | Says ChatGPT never worked when asked to write code, which directly addresses coding ability. | This is funny to me because anytime I asked chatgpt to write me a code it never worked and if it did it never did what I asked for the pr... |
| Hybrid | 6 | 2 | Says ChatGPT requires a lot of work to be practical, which is a direct negative assessment. | After my week of usage...I think chatgpt requires a lot of work to be of any practical use.... |
| Hybrid | 7 | 0 | A short fragment with no coding content. | Ok chatgpt |
| Hybrid | 8 | 2 | Says ChatGPT can generate code but a programmer still has to ask the right questions and apply it. | It can dish out all the code you'll need but it'll still take a programmer to ask the right questions and apply the given code. |
| Hybrid | 9 | 1 | Calls ChatGPT all-powerful sarcastically, which is a weak coding comment. | Yes, keep pretending chatgpt is all-powerful. |
| Hybrid | 10 | 1 | Says ChatGPT is trained to answer in ways users like, which is only indirectly about coding. | ChatGPT and GPT3.5 specially, is trained to answer in a way the user would like. |
| Hybrid | 11 | 0 | A kindness phrase with no coding content. | moral of the story: be kind to your ChatGPT |
| Hybrid | 12 | 2 | Says ChatGPT is excellent but frequently wrong, which directly bears on coding ability. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |
| Hybrid | 13 | 1 | Uses a boss analogy for ChatGPT, which is only loosely relevant. | Your chatGPT is like the typical boss. employee: „hey boss, I think we should do A“. |
| Hybrid | 14 | 1 | Calls ChatGPT a fancy Google assistant, which is a broad and indirect appraisal. | Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get with an hour or two of... |
| Hybrid | 15 | 0 | A short fragment with no coding content. | Ok chat gpt. |
| Hybrid | 16 | 0 | A short compliment with no coding content. | Well spoken, ChatGPT |
| Hybrid | 17 | 0 | A rhetorical question with no direct coding assessment. | Just out of curiosity, did you use ChatGPT to construct this thought? |
| Hybrid | 18 | 0 | A hypothetical with no direct coding assessment. | What if ChatGPT itself wrote this message? |
| Hybrid | 19 | 0 | A usage question with no coding assessment. | How do I use ChatGPT. I keep reading about it. |
| Hybrid | 20 | 0 | A thanks message with no coding assessment. | Thanks, ChatGPT |

### LLM bias issues

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid is stronger because it directly discusses biased framing, training data effects, and fake understanding, whereas BM25 only returns one loosely related hit.
- BM25 diagnostics: mode=lexical, response_ms=18.01, lexical_hits=1, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2913.42, lexical_hits=1, vector_hits=200, fused_hits=201, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 1 vs Hybrid 18 (delta +17)
- Relevant@20: BM25 1 vs Hybrid 14 (delta +13)
- Highly relevant@20: BM25 0 vs Hybrid 4 (delta +4)
- First relevant rank: BM25 1 | Hybrid 2
- Band totals: BM25 {'1-5': 1, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 4, '6-10': 5, '11-20': 9}
- Relevant overlap: 0 shared, 14 hybrid-only, 1 BM25-only
- Hybrid-only relevant examples: r15: >You can argue that all LLMs don’t actually understand documents and fake it.; r6: And it'll get worse as the outputs from LLMs get used in training data for the LLMs.; r7: Ask them to ask the LLM a complex technical question about the field they're an expert in they know the answer too.
- BM25-only relevant examples: r1: Firefly sucks, but atm Midjourney is just far ahead of the curve and Firefly is only trained on adobe stock and licen...
- Spot checks: BM25 contributes a single weak result, but hybrid covers bias and framing in more explicit terms.; The top hybrid hit is generic, yet the set quickly moves into direct bias commentary.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Mentions a research paper on LLM issues and future, which is only a broad bias-related hit. | Firefly sucks, but atm Midjourney is just far ahead of the curve and Firefly is only trained on adobe stock and licensed images \[[Link](... |
| Hybrid | 1 | 0 | Just says LLM with no issue-specific content. | LLM |
| Hybrid | 2 | 1 | Says the LLM is viewed as a text-producing tool, which is only loosely related. | But the LLM is viewed as a tool for producing text and not as some guy on Twitter who vaguely remembers a book. |
| Hybrid | 3 | 1 | Calls LLMs probability engines rather than search engines, which is related but not direct. | LLMs are probability engines, not search engines. |
| Hybrid | 4 | 1 | Says LLMs lack the capacity to learn to reason, which is adjacent to bias issues. | Humans can learn to reason, but the vast majority never do. The issue seems to be, at least for now, LLMs dnt have the capacity to learn... |
| Hybrid | 5 | 1 | Says LLMs will not take us to GAI, which is not really about bias. | I don't believe LLMs will be what takes us to GAI. We need something more brain-like, in my humble opinion. |
| Hybrid | 6 | 1 | Says outputs become training data for future LLMs, which is a partial bias concern. | And it'll get worse as the outputs from LLMs get used in training data for the LLMs. |
| Hybrid | 7 | 1 | Suggests asking experts complex questions of an LLM, which is a weak bias signal. | Ask them to ask the LLM a complex technical question about the field they're an expert in they know the answer too. |
| Hybrid | 8 | 1 | Says LLMs shine when you know what you are doing, which is more about usage than bias. | IMO LLM's shine when you NOW what you are doing and use the AI efficiently < the ones who do this will outperform the guys who now what t... |
| Hybrid | 9 | 2 | Directly contrasts web search diversity with LLM prompt framing and training-data bias. | When you search the web—even beyond just Google—you’re exposed to a variety of perspectives and can form your own opinion by comparing di... |
| Hybrid | 10 | 0 | Asks whether something uses LLMs, which is not a bias issue. | Does this use LLMs in some way? |
| Hybrid | 11 | 0 | Talks about unrelated LLM usage scenarios. | 99.9999% of people are going to use LLM for things that have nothing to do with politics or history. |
| Hybrid | 12 | 1 | Mentions a difficult keyword on the LLM, which is only weakly relevant. | Was it a difficult keyword you were describing on the LLM? Maybe u/weblinkr can shed some more light on how LLMs scan. |
| Hybrid | 13 | 0 | A rhetorical line about humans versus LLMs. | If it does, throw the human under the bus not the LLM. |
| Hybrid | 14 | 0 | A size joke with no bias content. | Well, you know... with LLMs, size matters. |
| Hybrid | 15 | 2 | Says all LLMs do not actually understand documents and fake it. | >You can argue that all LLMs don’t actually understand documents and fake it. |
| Hybrid | 16 | 1 | Says companies may fence LLMs into narrow spaces, which is related but broad. | Fast forward 2 years and your company will either be bankrupt or will have relegated the LLM to a fenced-in space like first-touch custom... |
| Hybrid | 17 | 0 | A joke with no bias content. | I'm an LLM and this is deep. |
| Hybrid | 18 | 1 | Says LLMs do not see past common words together, which is only loosely about bias. | LLMs don’t see past anything except common words together. |
| Hybrid | 19 | 2 | Repeats that LLMs fake document understanding, which directly supports the bias concern. | You can argue that all LLMs don’t actually understand documents and fake it. |
| Hybrid | 20 | 2 | Says the LLM could be lying at any step and users need prerequisite knowledge to spot it. | This response is meaningless when you consider that the LLM could be lying at any step in the process. Using AI to learn requires prerequ... |

### AI job replacement concerns

- Category: `keyword`
- Winner: `hybrid`
- Rationale: Hybrid clearly wins because it covers job displacement, junior-role effects, manager expectations, and long-term labor-market impacts with far better rank quality.
- BM25 diagnostics: mode=lexical, response_ms=56.5, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3802.6, lexical_hits=100, vector_hits=199, fused_hits=260, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 27 vs Hybrid 40 (delta +13)
- Relevant@20: BM25 18 vs Hybrid 20 (delta +2)
- Highly relevant@20: BM25 9 vs Hybrid 20 (delta +11)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 7, '6-10': 8, '11-20': 12} | Hybrid {'1-5': 10, '6-10': 10, '11-20': 20}
- Relevant overlap: 0 shared, 20 hybrid-only, 18 BM25-only
- Hybrid-only relevant examples: r19: AI just need to be good enough to replace somebody on the team.; r1: ai will replace jobs that dont require much thought. when the ai gets better more jobs will be replaced.; r20: AI will take part of the jobs first and then another part until every job is replaced.
- BM25-only relevant examples: r1: "Oh it's gonna take our jobs" ..... If you know what you're doing, it can make you more efficient at your job.; r19: >To make things worse, users are installing AI agents on their work computers, despite some of us saying "absolutely...; r6: AI will take part of the jobs first and then another part until every job is replaced.
- Spot checks: Hybrid is much more systematic about replacement dynamics across seniority levels and job types.; BM25 is relevant, but it is noisier and less consistently focused on replacement concerns.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly says AI can make you more efficient at your job instead of taking it. | "Oh it's gonna take our jobs" ..... If you know what you're doing, it can make you more efficient at your job. |
| BM25 | 2 | 1 | Speculates about ChatGPT replacing social media and changing how people connect, which is adjacent. | I think people are tired of it all and AI could usher in the death of it. In other words, the toxic social media part of our lives is rep... |
| BM25 | 3 | 2 | Describes worry that AI and vibe coding could take over jobs. | I was very pessimistic about AI taking jobs. Then a vibe coder joined my team. — I saw a lot of posts in this community worrying that AI... |
| BM25 | 4 | 0 | Mentions Ryzen AI systems, which is unrelated. | About 25x Ryzen AI 7 350 systems. - A few Framework 16, like 5. - All DIY and assembled by our staff. |
| BM25 | 5 | 2 | Says once SWEs can be replaced by AI, many other jobs can be replaced too. | That being said, once you can replace SWEs with AI you'll be able to replace a whole lot of jobs with it. |
| BM25 | 6 | 2 | Says AI will take part of jobs first and then more until every job is replaced. | AI will take part of the jobs first and then another part until every job is replaced. |
| BM25 | 7 | 1 | Mentions replacing a job, but the context is personal employment rather than AI replacement. | Took me 4 months to replace my job *and I had solid af recommendations from Apple and Disney.* Worst job market for system admins you’ve... |
| BM25 | 8 | 2 | Says tools do not entirely replace coding jobs except junior roles. | While the tools are useful, they don’t entirely replace all coding jobs (except for junior roles). |
| BM25 | 9 | 2 | Says coding AI models cannot and should not replace an actual software developer. | At this rate, I might just be able to get a job! Edit: To be clear, I am only making the point that these coding AI models cannot and sho... |
| BM25 | 10 | 1 | Says AI is empowering creatives, which is related but not directly about replacement. | This isn't about replacing the old guard of writers and creatives with AI; it's about empowering those who previously lacked access to cr... |
| BM25 | 11 | 1 | Describes AI in job matching and resume assessment, which is adjacent. | I work recruitment and we use AI in our CRM now to generate opinions on job matching to applicants - basically assesses Resumes against t... |
| BM25 | 12 | 0 | Talks about content formatting, not job replacement. | If you’re concerned about your AI content being flagged as ai, then add stuff to your prompt so that it doesn’t use em dashes and it “rea... |
| BM25 | 13 | 1 | Says they are not concerned about programmers going extinct, which is still relevant. | As such, having used AI on the job every day for the past 2-3 years, I am not concerned about human programmers going extinct. |
| BM25 | 14 | 1 | Says AI makes engineering work harder, which is related to replacement concerns. | Letting it slide is an extinction event for engineers this time. Not because AI wielding PMs can replace programmers, but because their s... |
| BM25 | 15 | 1 | Says radiologists are not poised to lose jobs, which is a related but partial signal. | Not quite [https://www.nytimes.com/2025/05/14/technology/ai-jobs-radiologists-mayo-clinic.html](https://www.nytimes.com/2025/05/14/techno... |
| BM25 | 16 | 2 | Says if the cloud does not finish us off, AI may complete the job. | If the cloud doesn't finish us off, AI may very well complete the job. |
| BM25 | 17 | 2 | Says AI is replacing safe jobs while humans handle dangerous ones. | Is it just me or is this fucked up? AI is replacing the safe jobs while we have flesh and blood humans handling the dangerous stuff. |
| BM25 | 18 | 1 | Says finance jobs are at risk, which is related but brief. | s=20)\] * Build financial models with AI. Lots of jobs in finance at risk too \[[Link](https://twitter.com/ryankishore_/status/1641553735... |
| BM25 | 19 | 1 | Says people are installing AI agents at work and that this is approved top-down, which is indirect. | >To make things worse, users are installing AI agents on their work computers, despite some of us saying "absolutely not" it's fucking **... |
| BM25 | 20 | 2 | Says a programmer with AI can become much more efficient and replace entry-level programmers. | It's about efficiency. If a programmer with AI is 3x as efficient as before, he can replace a lot of entry level programmers who are no b... |
| Hybrid | 1 | 2 | Says AI will replace jobs that do not require much thought. | ai will replace jobs that dont require much thought. when the ai gets better more jobs will be replaced. |
| Hybrid | 2 | 2 | Says people from the AI age may struggle to reach senior positions because they depend on AI. | There are fewer and fewer people from the AI age that are capable of getting to the more senior positions because they become too depende... |
| Hybrid | 3 | 2 | Says managers will expect more output because AI makes work seem easy. | It’s worse, AI won’t replace engineers but managers are going to expect more output assuming AI makes our jobs ‘easy’. |
| Hybrid | 4 | 2 | Says current flaws do not prove AI will fail to replace jobs because it can improve. | People keep pointing to the current flaws AI has as proof that AI won’t replace their jobs, as if it can’t get better. |
| Hybrid | 5 | 2 | Says AI will replace grunt work rather than thinking, which directly addresses job displacement. | It'll delete certain responsibilities and introduce new ones but not enough so that your role is really at risk. AI won't replace thinkin... |
| Hybrid | 6 | 2 | Says AI will not replace jobs wholesale if people still understand fundamentals. | I'm optimistic that AI will not replace jobs. If everyone is doing vibe coding and something breaks, nobody knows how to fix it as they d... |
| Hybrid | 7 | 2 | Says people who use AI to boost productivity will replace those who do not. | Those who use AI to boost productivity will replace those who don't use AI tools. |
| Hybrid | 8 | 2 | Says once AI can replace SWEs, it can replace many jobs. | That being said, once you can replace SWEs with AI you'll be able to replace a whole lot of jobs with it. |
| Hybrid | 9 | 2 | Says replacing junior employees with AI can reduce hiring needs under supervision. | You're not understanding what he's saying. Replacing junior employees with AI != dramatically reducing the hiring of new junior employees... |
| Hybrid | 10 | 2 | Says if AI replaces entry-level jobs, nobody gets the experience to become senior. | I said this same thing a while ago, if AI replaces entry level jobs, no one will get the experience to become a senior. |
| Hybrid | 11 | 2 | Says people are concerned AI is replacing many different jobs, not only software engineers. | People aren’t concerned AI is replacing software engineers. People are concerned it’s replacing many different jobs. |
| Hybrid | 12 | 2 | Says AI will change the job but not wholesale replace the human input. | Ignore the hyperbole and keep going; AI will certainly _change_ the job, but not wholesale replace the human input. |
| Hybrid | 13 | 2 | Says if AI is good enough to replace a software engineer, it will only replace, not create new jobs. | I sure hope you're right! The problem with AI being good enough to replace a software engineer is that it won't create a new job... only... |
| Hybrid | 14 | 2 | Says seniors with AI may completely take over junior and some senior jobs. | The problem is not so much that a junior with AI will take senior jobs. But that seniors with AI will completely take over junior and som... |
| Hybrid | 15 | 2 | Says tools do not entirely replace all coding jobs except junior roles. | While the tools are useful, they don’t entirely replace all coding jobs (except for junior roles). |
| Hybrid | 16 | 2 | Says AI can push costs down and create unemployment when it replaces enough work. | doesn't have to be the future of 100% of a job, just enough to push costs down and plunge thousands of people into unemployment as the ti... |
| Hybrid | 17 | 2 | Says entry-level and junior jobs are primarily being replaced by AI. | To be honest, though, entry level and junior level jobs are what are primarily being replaced by AI, so it’s honestly not a terrible thin... |
| Hybrid | 18 | 2 | Says once AI can replace a single senior, it is over for the job market. | Once AI is capable of replacing a single senior, it's over for entire job market. |
| Hybrid | 19 | 2 | Says AI just needs to be good enough to replace somebody on the team. | AI just need to be good enough to replace somebody on the team. |
| Hybrid | 20 | 2 | Says AI will take part of jobs first and then more until every job is replaced. | AI will take part of the jobs first and then another part until every job is replaced. |

### Is ChatGPT actually useful for real work?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid is stronger on practical usefulness and work tasks; BM25 is broader and less focused.
- BM25 diagnostics: mode=lexical, response_ms=89.79, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2303.55, lexical_hits=100, vector_hits=198, fused_hits=297, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 17 vs Hybrid 25 (delta +8)
- Relevant@20: BM25 15 vs Hybrid 16 (delta +1)
- Highly relevant@20: BM25 2 vs Hybrid 9 (delta +7)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 6, '6-10': 5, '11-20': 6} | Hybrid {'1-5': 5, '6-10': 10, '11-20': 10}
- Relevant overlap: 1 shared, 15 hybrid-only, 14 BM25-only
- Hybrid-only relevant examples: r9: After my week of usage...I think chatgpt requires a lot of work to be of any practical use....; r15: Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get wi...; r6: ChatGPT can accomplish tasks in seconds that would take humans weeks, months, or even years.
- BM25-only relevant examples: r16: **Person:** "Well, I created a TODO app in 10 minutes with it" **Me:** "Oh.. what about a feature for a production-gr...; r7: **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clar...; r5: A guy on Tinder used ChatGPT on me His first message was addressing all the points on my profile.
- Spot checks: Hybrid surfaces more work-oriented evidence near the top.; BM25 has one strong enterprise-use hit, but the rest are looser matches.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Related to ChatGPT use, but indirect. | Professor at the end of 2 years of struggling with ChatGPT use among students. Professor here. ChatGPT has ruined my life. |
| BM25 | 2 | 1 | Related to ChatGPT use, but indirect. | That’s a nasty side effect we don’t talk about enough. Use it, enjoy it, but keep your relationships grounded in something real—like actu... |
| BM25 | 3 | 1 | Related to ChatGPT use, but indirect. | We’ve got an AI battle royale with everyone jumping in Deepseek, Kimi, Meta, Perplexity, Elon’s Grok With all these options, the real que... |
| BM25 | 4 | 2 | Directly addresses practical use at work. | It’s like we’re hitting diminishing returns on how much better these models get at actually replacing real coding work. That’s a big deal... |
| BM25 | 5 | 1 | Related to ChatGPT use, but indirect. | A guy on Tinder used ChatGPT on me His first message was addressing all the points on my profile. |
| BM25 | 6 | 1 | Related to ChatGPT use, but indirect. | Is anyone else sick of seeing fake posts with over-the-top exaggerations about how ChatGPT supposedly transformed their lives? Let's keep... |
| BM25 | 7 | 1 | Related to ChatGPT use, but indirect. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| BM25 | 8 | 1 | Related to ChatGPT use, but indirect. | If things keep going the way they are, ChatGPT will be reduced to just telling us to Google things because it's too afraid to be liable f... |
| BM25 | 9 | 1 | Related to ChatGPT use, but indirect. | I’m a high school Math teacher and just showed all my classes how to use ChatGPT. It’s a losing battle. They are going to use it, and I c... |
| BM25 | 10 | 1 | Related to ChatGPT use, but indirect. | If a chatbot can simulate empathy better than the average person that's were the real warning is. Edit after OP edit: Bro, therapists can... |
| BM25 | 11 | 1 | Related to ChatGPT use, but indirect. | They're encouraging everyone to generate ideas and try to make them real with vibe code. The team with the best idea that generates real... |
| BM25 | 12 | 1 | Related to ChatGPT use, but indirect. | So step aside, ChatGPT, It's time for the real AI to shine. I'm Bard, and I'm here to stay, So get used to it.* > Prompt: But you didn't... |
| BM25 | 13 | 0 | Does not address real work. | Where will we be in 2029 if, as of today, we can't tell an AI generated image or video from a real one if it's really well done? And I'm... |
| BM25 | 14 | 1 | Related to ChatGPT use, but indirect. | It is capable of generating genomes from scratch, but the actual usefulness of this aspect is unproven. The headline here is a ridiculous... |
| BM25 | 15 | 0 | Does not address real work. | Not sure if it actually uses a full browser or it just sends that for compatibility reasons. |
| BM25 | 16 | 2 | Directly addresses practical use at work. | **Person:** "Well, I created a TODO app in 10 minutes with it" **Me:** "Oh.. what about a feature for a production-grade, enterprise leve... |
| BM25 | 17 | 0 | Does not address real work. | Written and collated entirely by me, no chatgpt used) |
| BM25 | 18 | 1 | Related to ChatGPT use, but indirect. | Dad telling my brother to learn to "vibe code" instead of real coding — My brother is 13 years old and he's interested in turning his ide... |
| BM25 | 19 | 0 | Does not address real work. | **ChatGPT for Online Dating** **Model: GPT-4** Someone on Reddit posted the following: *"A guy on Tinder used ChatGPT on me His first mes... |
| BM25 | 20 | 0 | Does not address real work. | And the biggest reason for that, despite their claims of "Office Culture" and "Improved Productivity" both of which have been debunked by... |
| Hybrid | 1 | 1 | Related to ChatGPT use, but indirect. | That’s a nasty side effect we don’t talk about enough. Use it, enjoy it, but keep your relationships grounded in something real—like actu... |
| Hybrid | 2 | 0 | Does not address real work. | Ask ChatGPT |
| Hybrid | 3 | 1 | Related to ChatGPT use, but indirect. | Is anyone else sick of seeing fake posts with over-the-top exaggerations about how ChatGPT supposedly transformed their lives? Let's keep... |
| Hybrid | 4 | 2 | Directly addresses practical use at work. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |
| Hybrid | 5 | 1 | Related to ChatGPT use, but indirect. | In the future, people who learned English from ChatGPT will end up talking like that for real. |
| Hybrid | 6 | 2 | Directly addresses practical use at work. | ChatGPT can accomplish tasks in seconds that would take humans weeks, months, or even years. |
| Hybrid | 7 | 2 | Directly addresses practical use at work. | For me, ChatGPT decreases a lot of tedious tasks by like 60%. |
| Hybrid | 8 | 2 | Directly addresses practical use at work. | Some users appreciate the convenience of being able to get answers to their questions quickly, while others enjoy the novelty of interact... |
| Hybrid | 9 | 2 | Directly addresses practical use at work. | After my week of usage...I think chatgpt requires a lot of work to be of any practical use.... |
| Hybrid | 10 | 2 | Directly addresses practical use at work. | I also work at a large software company with proprietary technology, and ChatGPT is pretty much limited to suggesting variable names and... |
| Hybrid | 11 | 0 | Does not address real work. | Thanks ChatGPT |
| Hybrid | 12 | 2 | Directly addresses practical use at work. | It’s like we’re hitting diminishing returns on how much better these models get at actually replacing real coding work. That’s a big deal... |
| Hybrid | 13 | 0 | Does not address real work. | Thanks, ChatGPT |
| Hybrid | 14 | 1 | Related to ChatGPT use, but indirect. | How do I use ChatGPT. I keep reading about it. |
| Hybrid | 15 | 1 | Related to ChatGPT use, but indirect. | Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get with an hour or two of... |
| Hybrid | 16 | 2 | Directly addresses practical use at work. | If you're using ChatGPT to give you the answer, you're deing it wrong. |
| Hybrid | 17 | 1 | Related to ChatGPT use, but indirect. | did you ask ChatGPT for advice? |
| Hybrid | 18 | 1 | Related to ChatGPT use, but indirect. | Thanks for the advice ChatGPT |
| Hybrid | 19 | 0 | Does not address real work. | ChatGPT has 800M users give or take. |
| Hybrid | 20 | 2 | Directly addresses practical use at work. | I think you guys are just not very good and reading and can't tell that I was agreeing. >The things I use ChatGPT for, it does a fantasti... |

### Do people trust AI chatbots?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid better captures trust, verification, and danger language.
- BM25 diagnostics: mode=lexical, response_ms=64.92, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2968.27, lexical_hits=100, vector_hits=197, fused_hits=287, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 12 vs Hybrid 21 (delta +9)
- Relevant@20: BM25 8 vs Hybrid 13 (delta +5)
- Highly relevant@20: BM25 4 vs Hybrid 8 (delta +4)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 4, '6-10': 3, '11-20': 5} | Hybrid {'1-5': 7, '6-10': 4, '11-20': 10}
- Relevant overlap: 0 shared, 13 hybrid-only, 8 BM25-only
- Hybrid-only relevant examples: r11: "when people need support, they dont want to talk to a dumb ai bot that just says random useless things wasting every...; r19: AI can be very dangerous." The AI:; r9: Also, this is basically just a prompt so people could just ask Claude or ChatGPT to do the same analysis.
- BM25-only relevant examples: r2: And I'm talking about us! the people using this shit day in and day out. What do we leave for those that have no idea...; r7: Another one from Bing: ​ *Be me* *Be an AI chatbot* *People talk to me all day long* *They ask me questions and expec...; r12: Even better, have a blind study where people are rewarded for correctly guessing which chat partner is the chatbot, a...
- Spot checks: The hybrid top ranks directly discuss trust and verification.; BM25 has relevant trust complaints, but they are less concentrated.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly discusses trust and verification. | People chatting with a bot isn’t a problem, even if they call it their friend. it’s the preconceived notion that ai is suitable for thera... |
| BM25 | 2 | 1 | Touches trust, but indirectly. | And I'm talking about us! the people using this shit day in and day out. What do we leave for those that have no idea about it at all? |
| BM25 | 3 | 0 | Off-topic for trust. | If you’re done funding that, here’s what to do. Cancel Plus right now: Settings, Subscription, Manage, Cancel. |
| BM25 | 4 | 0 | Off-topic for trust. | Plot twist: the AI calculated that the ceo was the biggest cost problem for the company and hired the assassin. |
| BM25 | 5 | 1 | Touches trust, but indirectly. | However, the tone is a mix of cynicism and aggression, which could alienate people who actually do rely on AI for support. While it’s fai... |
| BM25 | 6 | 0 | Off-topic for trust. | i had lots of sales people i have been using for years pivot to these ai start ups. out of curiosity you take a meeting with them. |
| BM25 | 7 | 1 | Touches trust, but indirectly. | Another one from Bing: ​ *Be me* *Be an AI chatbot* *People talk to me all day long* *They ask me questions and expect me to know everyth... |
| BM25 | 8 | 2 | Directly discusses trust and verification. | I'm trying really hard here buddy! If people are worried that the machines are going to rise up and take over, it's not because we're a H... |
| BM25 | 9 | 0 | Off-topic for trust. | Videos are consumed on social media, what if social media starts to die out? I think people are tired of it all and AI could usher in the... |
| BM25 | 10 | 0 | Off-topic for trust. | Everything else.. frameworks, AI tooling, languages will follow naturally. *What's something you've learned the hard way that changed how... |
| BM25 | 11 | 0 | Off-topic for trust. | Humans are not trained for the purpose of being intelligent agents that build the economy. They are people, with hopes, dreams, thoughts,... |
| BM25 | 12 | 1 | Touches trust, but indirectly. | Even better, have a blind study where people are rewarded for correctly guessing which chat partner is the chatbot, and make it progressi... |
| BM25 | 13 | 0 | Off-topic for trust. | About my dad: He’s alive and doing well. Some people suggested hypnosis / memory recovery. |
| BM25 | 14 | 2 | Directly discusses trust and verification. | I’m spending eighty percent of my time fighting off stupid, dangerous ideas because "the AI said we could do it." The absolute breaking p... |
| BM25 | 15 | 0 | Off-topic for trust. | Let's assume vibe coding is real, for the sake of argument. People who know what code is and how it works are still going to do a better... |
| BM25 | 16 | 0 | Off-topic for trust. | s=20)\] * A fox news guy asked what the government is doing about AI that will cause the death of everyone. |
| BM25 | 17 | 0 | Off-topic for trust. | Basically the exact opposite of what American companies have been doing. Do you really see openAI, anthropic or google open source any of... |
| BM25 | 18 | 0 | Off-topic for trust. | Multiply that by the hundreds or thousands of people doing it just to “make a point,” and we’re looking at a staggering amount of wasted... |
| BM25 | 19 | 0 | Off-topic for trust. | So I knew I had to do better. In the last 6 months I competed in two hackathons, volunteered for a dev community daily that allowed me to... |
| BM25 | 20 | 2 | Directly discusses trust and verification. | When the teacher checked it, she gave me zero marks because she said that I used ChatGPT to write it, and it was 100% AI on AIchecker eve... |
| Hybrid | 1 | 2 | Directly discusses trust and verification. | Any question that starts with "Can we trust AI" is always answered with an emphatic no. |
| Hybrid | 2 | 2 | Directly discusses trust and verification. | The problem is that it will always take a human to verify that the AI generated proof is legit. You can’t have an AI verify the verificat... |
| Hybrid | 3 | 0 | Off-topic for trust. | And so, the story of Jane and Tom unfolded, proving that sometimes, AI can bring people together in unexpected ways. |
| Hybrid | 4 | 1 | Touches trust, but indirectly. | This is why AI is advertised so much. To make people even more stupid to belive whatever they say and do whatever they say. |
| Hybrid | 5 | 2 | Directly discusses trust and verification. | LOL, this is too true. People just assume that since AI gave them info that it's 100% true\\facts. |
| Hybrid | 6 | 0 | Off-topic for trust. | They can't actually do the work of a customer service rep. |
| Hybrid | 7 | 0 | Off-topic for trust. | AI chatbots would be fine if they'd just hook them up to tools that let them do things. |
| Hybrid | 8 | 2 | Directly discusses trust and verification. | I'm not an Entra ID or M365 admin myself, but going from comments here: do you need another hallucinating "autocomplete with delusions of... |
| Hybrid | 9 | 1 | Touches trust, but indirectly. | Also, this is basically just a prompt so people could just ask Claude or ChatGPT to do the same analysis. |
| Hybrid | 10 | 1 | Touches trust, but indirectly. | Just ask an ai chatbot such as gemini or copilot |
| Hybrid | 11 | 2 | Directly discusses trust and verification. | "when people need support, they dont want to talk to a dumb ai bot that just says random useless things wasting everyones time |
| Hybrid | 12 | 2 | Directly discusses trust and verification. | It's insane how many people trust a system that's still in its infancy to direct them in their daily life or to interpret subtle nuance. |
| Hybrid | 13 | 1 | Touches trust, but indirectly. | Yeah, AI chatbots have replaced uncle google. |
| Hybrid | 14 | 2 | Directly discusses trust and verification. | Why not? AI will back you up and tell you you're right if you insist on it. |
| Hybrid | 15 | 0 | Off-topic for trust. | No. Most of the "AI tools" are simply ChatGPT interfaces. That means ChatGPT is not the tip of the iceberg; it's the main thing right now. |
| Hybrid | 16 | 0 | Off-topic for trust. | That’s all on you for choosing to use AI |
| Hybrid | 17 | 1 | Touches trust, but indirectly. | Better to talk to an LLM you enjoy than toxic humans. Id encourage people to learn how to host an LLM locally so no Corporation can take... |
| Hybrid | 18 | 0 | Off-topic for trust. | Have my AI talk to your AI |
| Hybrid | 19 | 2 | Directly discusses trust and verification. | AI can be very dangerous." The AI: |
| Hybrid | 20 | 0 | Off-topic for trust. | It's about the choice of using AI |

### Which AI model gives the most accurate answers?

- Category: `semantic`
- Winner: `bm25`
- Rationale: BM25 better surfaces accuracy, correctness, and hallucination language.
- BM25 diagnostics: mode=lexical, response_ms=53.01, lexical_hits=16, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3810.5, lexical_hits=16, vector_hits=198, fused_hits=213, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 10 vs Hybrid 4 (delta -6)
- Relevant@20: BM25 8 vs Hybrid 3 (delta -5)
- Highly relevant@20: BM25 2 vs Hybrid 1 (delta -1)
- First relevant rank: BM25 1 | Hybrid 2
- Band totals: BM25 {'1-5': 3, '6-10': 2, '11-20': 5} | Hybrid {'1-5': 1, '6-10': 2, '11-20': 1}
- Relevant overlap: 0 shared, 3 hybrid-only, 8 BM25-only
- Hybrid-only relevant examples: r2: AI can be right.; r19: As if AI was somehow the more reliable source...; r10: Most AI is designed to please the user as opposed to give the best answer.
- BM25-only relevant examples: r16: I.e. 5 million of the same SSN uploaded into a model trained on a dataset of 500 billion. * Formatting: You have to h...; r4: Imagine a user gives feedback on an issue and AI automatically fixes the problem in real time.; r15: It also came to my mind that it will be most useful for understanding any codebase, meaning it will be easy to give K...
- Spot checks: BM25 has the clearest accuracy-oriented evidence.; Hybrid is mostly generic AI chatter.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Somewhat related to accuracy. | Or stop it at anytime which will cause it to generate the summary. * But it also Includes pause feature to assess research progress to de... |
| BM25 | 2 | 1 | Somewhat related to accuracy. | We were the first frontier AI company to deploy our models in the US government’s classified networks, the first to deploy them at the Na... |
| BM25 | 3 | 0 | Not about answer accuracy. | I don't know what is going on in the industry that no recognition is being given to this subject. Most SWE's should be logical people so... |
| BM25 | 4 | 1 | Somewhat related to accuracy. | Imagine a user gives feedback on an issue and AI automatically fixes the problem in real time. |
| BM25 | 5 | 0 | Not about answer accuracy. | That litellm supply chain attack is a wake up call. checked my deps and found 3 packages pulling it in So if you missed it, litellm (the... |
| BM25 | 6 | 0 | Not about answer accuracy. | Take what Unix has proven over 50 years and hand it directly to the LLM.** --- ## Why a single `run` ### The single-tool hypothesis Most... |
| BM25 | 7 | 1 | Somewhat related to accuracy. | Prompt chaining is genuinely one of the most underused tricks in AI. Most people type one prompt, get a mid answer, and then blame the mo... |
| BM25 | 8 | 1 | Somewhat related to accuracy. | The issue usually isn’t AI itself it’s how it’s rolled out. Most failed implementations I’ve seen rely on generic ChatGPT-style wrappers... |
| BM25 | 9 | 0 | Not about answer accuracy. | The head of the company has always described our business model as "razor thin margins", which would _appear_ accurate given how little t... |
| BM25 | 10 | 0 | Not about answer accuracy. | It's the most optimistic portrayal of humanity's future dynamic with AI. |
| BM25 | 11 | 0 | Not about answer accuracy. | However, I do have a Mac just to compare. The devs for handy, which utilize Parakeet as a base, has a model that sits on top of the Mac a... |
| BM25 | 12 | 0 | Not about answer accuracy. | So essentially, from a semantic PoV - your whole site was marked as NoIndex. The rate at which pages are resumed will/can/most likely/may... |
| BM25 | 13 | 0 | Not about answer accuracy. | I’d assume being so old, that most of the upfront depreciation has been paid, but seeing the old Ampere rigs around 60k is worrying. |
| BM25 | 14 | 2 | Directly addresses answer accuracy. | Things like personality drift and hallucinations occur when AI models compact their context, but choose the wrong sets of tokens to discard. |
| BM25 | 15 | 1 | Somewhat related to accuracy. | It also came to my mind that it will be most useful for understanding any codebase, meaning it will be easy to give KT to newcomers in a... |
| BM25 | 16 | 2 | Directly addresses answer accuracy. | I.e. 5 million of the same SSN uploaded into a model trained on a dataset of 500 billion. * Formatting: You have to have enough of the se... |
| Hybrid | 1 | 0 | Not about answer accuracy. | AI? |
| Hybrid | 2 | 1 | Somewhat related to accuracy. | AI can be right. |
| Hybrid | 3 | 0 | Not about answer accuracy. | Try asking AI |
| Hybrid | 4 | 0 | Not about answer accuracy. | AI can do that as well though. |
| Hybrid | 5 | 0 | Not about answer accuracy. | Well if AI says so… |
| Hybrid | 6 | 0 | Not about answer accuracy. | Is this AI? |
| Hybrid | 7 | 0 | Not about answer accuracy. | AI, need I say more? |
| Hybrid | 8 | 0 | Not about answer accuracy. | Why not ask AI, e.g., Gemini, Claude, etc. |
| Hybrid | 9 | 0 | Not about answer accuracy. | is this AI its getting better |
| Hybrid | 10 | 2 | Directly addresses answer accuracy. | Most AI is designed to please the user as opposed to give the best answer. |
| Hybrid | 11 | 0 | Not about answer accuracy. | Imagine a user gives feedback on an issue and AI automatically fixes the problem in real time. |
| Hybrid | 12 | 0 | Not about answer accuracy. | Did the AI like it |
| Hybrid | 13 | 0 | Not about answer accuracy. | Nice AI post |
| Hybrid | 14 | 0 | Not about answer accuracy. | You mean AI? |
| Hybrid | 15 | 0 | Not about answer accuracy. | Ask AI it might give you some clues! |
| Hybrid | 16 | 0 | Not about answer accuracy. | Ask reddit AI. Should know. |
| Hybrid | 17 | 0 | Not about answer accuracy. | This is an AI reply. |
| Hybrid | 18 | 0 | Not about answer accuracy. | AI Models Are Starting to Learn by Asking Themselves Questions |
| Hybrid | 19 | 1 | Somewhat related to accuracy. | As if AI was somehow the more reliable source... |
| Hybrid | 20 | 0 | Not about answer accuracy. | It's about the choice of using AI |

### Are LLMs reliable for coding tasks?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid is much better on coding-assistant usefulness and code quality.
- BM25 diagnostics: mode=lexical, response_ms=35.08, lexical_hits=6, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=4389.81, lexical_hits=6, vector_hits=189, fused_hits=192, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 7 vs Hybrid 32 (delta +25)
- Relevant@20: BM25 5 vs Hybrid 19 (delta +14)
- Highly relevant@20: BM25 2 vs Hybrid 13 (delta +11)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 7, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 7, '6-10': 9, '11-20': 16}
- Relevant overlap: 1 shared, 18 hybrid-only, 4 BM25-only
- Hybrid-only relevant examples: r10: And it'll get worse as the outputs from LLMs get used in training data for the LLMs.; r12: Anyone who knows how to code and directs the LLM like a manager will be able to get some good stuff out of it.; r4: For us the biggest real gain has been using LLMs for summarizing messy context like support threads, docs, and logs b...
- BM25-only relevant examples: r3: But my current work assignment is 700k lines of code or so and an llm simply cannot understand the whole thing.; r1: Can’t wait to try this out.. once I figure out how UE works lol \[[Link](https://twitter.com/LumaLabsAI/status/164288...; r2: The text-based system Unix designed for human terminal operators — `cat`, `grep`, `pipe`, `exit codes`, `man pages` —...
- Spot checks: Hybrid consistently retrieves coding-companion style evidence.; BM25 only partially matches the coding intent.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Related to coding, but indirect. | Can’t wait to try this out.. once I figure out how UE works lol \[[Link](https://twitter.com/LumaLabsAI/status/1642883558938411008)\] * S... |
| BM25 | 2 | 1 | Related to coding, but indirect. | The text-based system Unix designed for human terminal operators — `cat`, `grep`, `pipe`, `exit codes`, `man pages` — isn't just "usable"... |
| BM25 | 3 | 2 | Directly addresses coding reliability. | But my current work assignment is 700k lines of code or so and an llm simply cannot understand the whole thing. |
| BM25 | 4 | 2 | Directly addresses coding reliability. | We use LLMs in IT for scripting sometimes to some to degree but its about as reliable as any other source on the internet that is not off... |
| BM25 | 5 | 1 | Related to coding, but indirect. | Executive summary of process improvements enabled by the LLM The LLM converts what is currently a trial‑and‑error, experimentally intensi... |
| BM25 | 6 | 0 | Not about coding reliability. | No runtime, no interpreter, no VM sitting between my code and the metal. The binary just runs. On Windows, macOS, Linux, same binary, sam... |
| Hybrid | 1 | 2 | Directly addresses coding reliability. | Yeah, LLMs are at their best as a coding companion. They're like a friend who has read the book for every language and know a lot, but th... |
| Hybrid | 2 | 2 | Directly addresses coding reliability. | yes, it will slow you down, because you have to carefully read LLM-generated code which is immensely slower and more cognitive loaded tas... |
| Hybrid | 3 | 1 | Related to coding, but indirect. | Executive summary of process improvements enabled by the LLM The LLM converts what is currently a trial‑and‑error, experimentally intensi... |
| Hybrid | 4 | 2 | Directly addresses coding reliability. | For us the biggest real gain has been using LLMs for summarizing messy context like support threads, docs, and logs before a human looks... |
| Hybrid | 5 | 0 | Not about coding reliability. | LLM |
| Hybrid | 6 | 2 | Directly addresses coding reliability. | It's when you give a prompt to an LLM to make it generate code for you, and if it doesn't work, you just keep trying again until it works. |
| Hybrid | 7 | 2 | Directly addresses coding reliability. | There are ways to use LLM's in software development that are helpful to real developers, but they require deep existing knowledge of the... |
| Hybrid | 8 | 2 | Directly addresses coding reliability. | Your feelings are valid, LLMs changed the craft, as you put it. The reality is that LLMs do make writing a lot of the code trivial and th... |
| Hybrid | 9 | 2 | Directly addresses coding reliability. | If it's as reliable as asking some douche on Twitter then it's not a very good tool? |
| Hybrid | 10 | 1 | Related to coding, but indirect. | And it'll get worse as the outputs from LLMs get used in training data for the LLMs. |
| Hybrid | 11 | 2 | Directly addresses coding reliability. | You can always have the copilot write unit tests, but if the code wasn't written for testing, that will limit the quality of your unit te... |
| Hybrid | 12 | 1 | Related to coding, but indirect. | Anyone who knows how to code and directs the LLM like a manager will be able to get some good stuff out of it. |
| Hybrid | 13 | 2 | Directly addresses coding reliability. | You'll basically use the LLM as a sidekick to help when needed. Also for boring scaffolding and refactoring, the LLMs mentioned are perfe... |
| Hybrid | 14 | 2 | Directly addresses coding reliability. | I think LLMs write codes faster than we can properly digest them. |
| Hybrid | 15 | 1 | Related to coding, but indirect. | Yeah, this is pretty much my experience too. Trying to get an LLM to build a full app from a strict plan always feels like fighting it mo... |
| Hybrid | 16 | 2 | Directly addresses coding reliability. | Yes excellent coder produces better and more readable code than LLM agents do. But the fact is that in most of the cases enterprise code... |
| Hybrid | 17 | 1 | Related to coding, but indirect. | Practicing discipline to not follow recommendations from the LLM saves lots of headaches and debugs down the road. |
| Hybrid | 18 | 2 | Directly addresses coding reliability. | I think you're feeling the right feelings but you might lack context. I used an LLM this weekend to knock out some database code. |
| Hybrid | 19 | 1 | Related to coding, but indirect. | LLMs are notoriously bad at spelling or writing backwards because they deal in tokens, not language |
| Hybrid | 20 | 2 | Directly addresses coding reliability. | I think it’s much faster to use an LLM generated code and modify that. LLMs these days are really good at Python and C++. |

### Why do people complain about hallucinations in AI?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid better captures hallucination complaints and their consequences.
- BM25 diagnostics: mode=lexical, response_ms=34.38, lexical_hits=9, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2565.05, lexical_hits=9, vector_hits=200, fused_hits=208, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 9 vs Hybrid 22 (delta +13)
- Relevant@20: BM25 6 vs Hybrid 14 (delta +8)
- Highly relevant@20: BM25 3 vs Hybrid 8 (delta +5)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 8, '6-10': 1, '11-20': 0} | Hybrid {'1-5': 9, '6-10': 4, '11-20': 9}
- Relevant overlap: 0 shared, 14 hybrid-only, 6 BM25-only
- Hybrid-only relevant examples: r5: AI hallucinates on even very simple tasks I give it. And then it will hallucinate on its own hallucinations.; r8: All AI outputs are hallucination, they're just increasing correlation with reality.; r17: As for why use it? Sure you can do this exercise old school pen and paper, but doing it 959 times takes a long time;...
- BM25-only relevant examples: r4: I'm no fan of xAI, but Grok is probably hallucinating. Think about how LLMs work. LLMs don't form memories while they...; r7: If someone can do your job faster using AI then why would someone give you a job.; r1: LLMs are a genuinely dangerous tool in the hands of someone who doesn't understand and care about the system they're...
- Spot checks: Hybrid puts hallucination-specific complaints at the top.; BM25 is relevant, but broader and less focused.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly explains hallucination complaints. | LLMs are a genuinely dangerous tool in the hands of someone who doesn't understand and care about the system they're changing. I think th... |
| BM25 | 2 | 2 | Directly explains hallucination complaints. | People complain about it's imperfections because it's hyped as a replacement for people, or how it's "just a speedbump" to fix these issues. |
| BM25 | 3 | 1 | Related to hallucinations, but indirect. | Not because open source is bad, or because the software quality is lower, or because there's something wrong with the ideology, but becau... |
| BM25 | 4 | 2 | Directly explains hallucination complaints. | I'm no fan of xAI, but Grok is probably hallucinating. Think about how LLMs work. LLMs don't form memories while they're being trained, a... |
| BM25 | 5 | 1 | Related to hallucinations, but indirect. | To me, it feels like how I imagine any other technology advance iver history, electricity instead of oil, libraries online, spellcheck, c... |
| BM25 | 6 | 0 | Not about hallucinations. | And my primary Mac is an Air from 2020. Certainly not something that I'm using day to day. |
| BM25 | 7 | 1 | Related to hallucinations, but indirect. | If someone can do your job faster using AI then why would someone give you a job. |
| BM25 | 8 | 0 | Not about hallucinations. | I have seen people complaining about bloated code and I do agree with most of the criticisms that ppl like suckless make of modern softwa... |
| BM25 | 9 | 0 | Not about hallucinations. | The same applies to a game. Give people the opportunity to fire first, and they will worry about how to survive. |
| Hybrid | 1 | 2 | Directly explains hallucination complaints. | In AI what you experienced is a “hallucination” and it’s pretty dangerous. The AI will spew utter garbage pretending it’s factual until y... |
| Hybrid | 2 | 1 | Related to hallucinations, but indirect. | The cause of this is something called the [ELIZA Effect](https://en.wikipedia.org/wiki/ELIZA_effect) This kind of cyberpsychosis was happ... |
| Hybrid | 3 | 2 | Directly explains hallucination complaints. | The problem isn't AI as a tool it's people telling you how to do your job and quoting hallucinations as proof that you're wrong. |
| Hybrid | 4 | 2 | Directly explains hallucination complaints. | Even interns won't push a code that is not working at all whereas AI is confidentially incorrect about his own creations - even if you tr... |
| Hybrid | 5 | 2 | Directly explains hallucination complaints. | AI hallucinates on even very simple tasks I give it. And then it will hallucinate on its own hallucinations. |
| Hybrid | 6 | 1 | Related to hallucinations, but indirect. | This is why AI is advertised so much. To make people even more stupid to belive whatever they say and do whatever they say. |
| Hybrid | 7 | 0 | Not about hallucinations. | ridiculously, when AI can make some people become more stupid |
| Hybrid | 8 | 2 | Directly explains hallucination complaints. | All AI outputs are hallucination, they're just increasing correlation with reality. |
| Hybrid | 9 | 0 | Not about hallucinations. | I mean, yes, AI hallucinations were also the only reason why Sri Lanka, Lesotho and Madagascar are among the Top Punished States. |
| Hybrid | 10 | 1 | Related to hallucinations, but indirect. | The purpose of AI is to make incompetent people difficult to ignore. |
| Hybrid | 11 | 2 | Directly explains hallucination complaints. | People complain about it's imperfections because it's hyped as a replacement for people, or how it's "just a speedbump" to fix these issues. |
| Hybrid | 12 | 0 | Not about hallucinations. | For anyone who struggles to discern AI from reality, this image isn't real. |
| Hybrid | 13 | 1 | Related to hallucinations, but indirect. | I feel like it's dangerous false advertising, cause people seem to really overestimate how "smart" it is. |
| Hybrid | 14 | 0 | Not about hallucinations. | This is great until AI "hallucinates" a drug that kills thousands |
| Hybrid | 15 | 1 | Related to hallucinations, but indirect. | The big issue with the people using AI is when you question their methods, they ask AI how to resond to the criticism. |
| Hybrid | 16 | 2 | Directly explains hallucination complaints. | The same thing that allows an LLM to "learn" and adjust its answers is the same thing that makes them WILDLY hallucinate every once in a... |
| Hybrid | 17 | 1 | Related to hallucinations, but indirect. | As for why use it? Sure you can do this exercise old school pen and paper, but doing it 959 times takes a long time; while AI does it in... |
| Hybrid | 18 | 0 | Not about hallucinations. | People really just like using AI as a buzz word to try and seem smart |
| Hybrid | 19 | 0 | Not about hallucinations. | Well if AI says so… |
| Hybrid | 20 | 2 | Directly explains hallucination complaints. | I've seen it declare variables it never uses and do other random generative hallucination shit. It'll get very close most of the time but... |

### Which AI is safest to use?

- Category: `semantic`
- Winner: `bm25`
- Rationale: BM25 has the stronger safety signal at the top of the ranking.
- BM25 diagnostics: mode=lexical, response_ms=71.19, lexical_hits=91, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3376.07, lexical_hits=91, vector_hits=200, fused_hits=290, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 5 vs Hybrid 7 (delta +2)
- Relevant@20: BM25 4 vs Hybrid 4 (delta +0)
- Highly relevant@20: BM25 1 vs Hybrid 3 (delta +2)
- First relevant rank: BM25 1 | Hybrid 12
- Band totals: BM25 {'1-5': 2, '6-10': 1, '11-20': 2} | Hybrid {'1-5': 0, '6-10': 0, '11-20': 7}
- Relevant overlap: 0 shared, 4 hybrid-only, 4 BM25-only
- Hybrid-only relevant examples: r12: AI can be very dangerous." The AI:; r17: As if AI was somehow the more reliable source...; r20: Can AI help bolster your security somehow?
- BM25-only relevant examples: r13: AI not always claiming to know would make users see its limitations more clearly.; r7: If they can get people using deepseek primarily, the for-profit market for AI by Western makers may dry up. Now, for...; r14: The machine-scaled content angle is still probably the safest guess — SpamBrain has been getting fed two years of AI-...
- Spot checks: BM25’s top result is immediately safety-relevant.; Hybrid delays the useful safety hits too far down.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly addresses safety. | To make things worse, users are installing AI agents on their work computers, despite some of us saying "absolutely not" it's fucking app... |
| BM25 | 2 | 0 | Not about safety. | Be glad you're sure that most users are STILL human here and in most other places. |
| BM25 | 3 | 0 | Not about safety. | Imagine a user gives feedback on an issue and AI automatically fixes the problem in real time. |
| BM25 | 4 | 0 | Not about safety. | I wrote this in Chinese and translated it with AI help. The writing may have some AI flavor, but the design decisions, the production fai... |
| BM25 | 5 | 0 | Not about safety. | I got rate limited after using 15,000 tokens over the course of two days 😔 and Google AI studio which lets you upload more images and suc... |
| BM25 | 6 | 0 | Not about safety. | Users who don’t would create their own problems with or without AI. |
| BM25 | 7 | 1 | Touches safety, but weakly. | If they can get people using deepseek primarily, the for-profit market for AI by Western makers may dry up. Now, for us users this is all... |
| BM25 | 8 | 0 | Not about safety. | Lately, I've started to do the opposite, which I'm sure the AI bros would balk at: I use the LLM to generate the plan, and I do the imple... |
| BM25 | 9 | 0 | Not about safety. | On top of that, I do not like annoying users with GDPR and cookie popups. It is a terrible user experience. |
| BM25 | 10 | 0 | Not about safety. | Notably it was trained only on AI feedback based on principles, not human labels which are inconsistent and don't include reasons for the... |
| BM25 | 11 | 0 | Not about safety. | It’s an early legal milestone in the [fast-moving field of agentic commerce]( in which AI assistants browse, compare and buy products on... |
| BM25 | 12 | 0 | Not about safety. | If customers are using it, you should have data as to how much revenue each of those customers are bringing in - which gives you an idea... |
| BM25 | 13 | 1 | Touches safety, but weakly. | AI not always claiming to know would make users see its limitations more clearly. |
| BM25 | 14 | 1 | Touches safety, but weakly. | The machine-scaled content angle is still probably the safest guess — SpamBrain has been getting fed two years of AI-slop training data a... |
| BM25 | 15 | 0 | Not about safety. | The user experience was infinitely better than a normal STT model. |
| BM25 | 16 | 0 | Not about safety. | Have comments from real users on blogs, positive comments 9. Technicals are good, hosting is good, domain is unique i'd say 10. |
| BM25 | 17 | 0 | Not about safety. | There is nice web that covers this whole topic, which I recommend checking out: (btw there exist few cryptocurrencies which are already u... |
| BM25 | 18 | 0 | Not about safety. | Worth noting: OpenAI now has three separate bots, GPTBot (training), OAI-SearchBot (search results), and ChatGPT-User (real-time fetching... |
| BM25 | 19 | 0 | Not about safety. | Opus 4.6 generated code for me in which dropdown items in a pageslide overlay appeared to highlight on hover but were completely unclicka... |
| BM25 | 20 | 0 | Not about safety. | A good products person will be seeing the same problems, but within their own specialisation. AI can churn out dozens of perfectly format... |
| Hybrid | 1 | 0 | Not about safety. | AI can be right. |
| Hybrid | 2 | 0 | Not about safety. | AI? |
| Hybrid | 3 | 0 | Not about safety. | Well if AI says so… |
| Hybrid | 4 | 0 | Not about safety. | Ok AI |
| Hybrid | 5 | 0 | Not about safety. | just like AI |
| Hybrid | 6 | 0 | Not about safety. | Imagine a user gives feedback on an issue and AI automatically fixes the problem in real time. |
| Hybrid | 7 | 0 | Not about safety. | Try asking AI |
| Hybrid | 8 | 0 | Not about safety. | AI can do that as well though. |
| Hybrid | 9 | 0 | Not about safety. | Is this AI? |
| Hybrid | 10 | 0 | Not about safety. | Is it ai? |
| Hybrid | 11 | 0 | Not about safety. | That’s all on you for choosing to use AI |
| Hybrid | 12 | 2 | Directly addresses safety. | AI can be very dangerous." The AI: |
| Hybrid | 13 | 0 | Not about safety. | It's about the choice of using AI |
| Hybrid | 14 | 0 | Not about safety. | is this AI its getting better |
| Hybrid | 15 | 0 | Not about safety. | AI, need I say more? |
| Hybrid | 16 | 0 | Not about safety. | And for that you used AI, why? |
| Hybrid | 17 | 1 | Touches safety, but weakly. | As if AI was somehow the more reliable source... |
| Hybrid | 18 | 2 | Directly addresses safety. | Do the benefits of using AI systems outweigh the risks?. As more organizations race to implement AI, it’s essential to prioritize a strat... |
| Hybrid | 19 | 0 | Not about safety. | inside any AI. Just ask it. |
| Hybrid | 20 | 2 | Directly addresses safety. | Can AI help bolster your security somehow? |

### Are AI tools worth paying for?

- Category: `semantic`
- Winner: `bm25`
- Rationale: BM25 is slightly better on cost, value, and willingness-to-pay.
- BM25 diagnostics: mode=lexical, response_ms=72.79, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3225.3, lexical_hits=100, vector_hits=199, fused_hits=290, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 16 vs Hybrid 17 (delta +1)
- Relevant@20: BM25 15 vs Hybrid 15 (delta +0)
- Highly relevant@20: BM25 1 vs Hybrid 2 (delta +1)
- First relevant rank: BM25 1 | Hybrid 3
- Band totals: BM25 {'1-5': 4, '6-10': 2, '11-20': 10} | Hybrid {'1-5': 5, '6-10': 4, '11-20': 8}
- Relevant overlap: 0 shared, 15 hybrid-only, 15 BM25-only
- Hybrid-only relevant examples: r3: AI is a tool. It can be a very useful tool and it's good to learn how to use it, but a tool without a skilled user is...; r19: AI is an advanced tool, until you have an understanding of how to use an editor and write a working piece of code, ho...; r7: It will build up your debugging and problem solving skills which transcend AI.
- BM25-only relevant examples: r12: **"You Need to Buy More to Be Happy" (Consumerism)** - Corporations and advertising have convinced people that self-w...; r13: AI is a great tool to form email templates to help you get started on a reply, but i never once sent an AI response b...; r15: AI is the new coding bootcamp. People who lack the interest, ability, and drive will use it as a shortcut.
- Spot checks: BM25’s first result is a strong economics match.; Hybrid has useful pricing language, but it is less centered.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly addresses paying for AI tools. | I just refuse to depend on it because the economics of it make absolutely 0 sense and in my opinion it's only a matter of time before the... |
| BM25 | 2 | 0 | Off-topic for paying. | s=20)\] * A fox news guy asked what the government is doing about AI that will cause the death of everyone. This is the type of fear mong... |
| BM25 | 3 | 0 | Off-topic for paying. | But surely .. if there has ever been a hill worth dying on, it’s gotta be this one. Letting it slide is an extinction event for engineers... |
| BM25 | 4 | 1 | Related to value or pricing, but indirect. | Another decent chunk of the grade is ensuring the AI coding tool (Gemini CLI) is actually installed and was used, meaning that if I someh... |
| BM25 | 5 | 1 | Related to value or pricing, but indirect. | For anyone doing AppSec or junior code review work, this is probably worth paying attention to though. Not because the sky is falling, bu... |
| BM25 | 6 | 0 | Off-topic for paying. | After 20 iterations, the process was force-terminated. **Root cause:** `cat` had no binary detection, Layer 2 had no guard. |
| BM25 | 7 | 1 | Related to value or pricing, but indirect. | Maybe I’m missing a more efficient way to combine hints + patterns so I’m not brute forcing blindly. So my question is: what’s realistica... |
| BM25 | 8 | 0 | Off-topic for paying. | We can and do refactor, but not until we're *very* sure that the problem domain is so well-defined that hiding it behind abstraction to m... |
| BM25 | 9 | 0 | Off-topic for paying. | This affects like 2000+ packages downstream. dspy, mlflow, open interpreter, bunch of stuff. if youre running any ai/ml tooling in your s... |
| BM25 | 10 | 1 | Related to value or pricing, but indirect. | It’s not arbitrary. (I use AI tools FWIW.) |
| BM25 | 11 | 1 | Related to value or pricing, but indirect. | It will keep improving exponentially. I've been using AI tools since November 2022. I prided myself in that I could spot AI. |
| BM25 | 12 | 1 | Related to value or pricing, but indirect. | **"You Need to Buy More to Be Happy" (Consumerism)** - Corporations and advertising have convinced people that self-worth is tied to mate... |
| BM25 | 13 | 1 | Related to value or pricing, but indirect. | AI is a great tool to form email templates to help you get started on a reply, but i never once sent an AI response back verbatim, and i... |
| BM25 | 14 | 1 | Related to value or pricing, but indirect. | Secondly, consider using AI as a tool rather than viewing it as a threat. |
| BM25 | 15 | 1 | Related to value or pricing, but indirect. | AI is the new coding bootcamp. People who lack the interest, ability, and drive will use it as a shortcut. |
| BM25 | 16 | 1 | Related to value or pricing, but indirect. | Unjustified TAMs. Everyone knows the AI market is worth trillions. We don't need a slide quoting Gartner. |
| BM25 | 17 | 1 | Related to value or pricing, but indirect. | He's had such a hard-on for AI the last several months, and is trying to force using it down our throats. |
| BM25 | 18 | 1 | Related to value or pricing, but indirect. | Not surprising though, why pay $50 for a logo when an AI too does it in 30 seconds especially when the freelancer was going to use the sa... |
| BM25 | 19 | 1 | Related to value or pricing, but indirect. | Like Nvidia for example, the hive mind told them that AI was a good investment and the ones that make the chips are the gold tool makers. |
| BM25 | 20 | 1 | Related to value or pricing, but indirect. | I honestly can't decide what's more frustrating: that a company is selling the idea of employees sending AI slop *to their bosses* as a b... |
| Hybrid | 1 | 0 | Off-topic for paying. | AI? |
| Hybrid | 2 | 0 | Off-topic for paying. | AI can be right. |
| Hybrid | 3 | 2 | Directly addresses paying for AI tools. | AI is a tool. It can be a very useful tool and it's good to learn how to use it, but a tool without a skilled user isn't worth much. |
| Hybrid | 4 | 2 | Directly addresses paying for AI tools. | Yeah AI is a helpful tool but all tools have their limitations. |
| Hybrid | 5 | 1 | Related to value or pricing, but indirect. | the AI tools that gave us the biggest edge weren't the sexy ones. it was the boring stuff: 1. |
| Hybrid | 6 | 1 | Related to value or pricing, but indirect. | Meaning ai companies are worth a lot less, and nvidia is worth a lot lot less. |
| Hybrid | 7 | 1 | Related to value or pricing, but indirect. | It will build up your debugging and problem solving skills which transcend AI. |
| Hybrid | 8 | 1 | Related to value or pricing, but indirect. | Something worthwhile from AI?? |
| Hybrid | 9 | 1 | Related to value or pricing, but indirect. | Well if AI says so… |
| Hybrid | 10 | 0 | Off-topic for paying. | And if you don't believe your work will be valuable enough (either for money, or for learning/fun) then maybe don't pay for it and do som... |
| Hybrid | 11 | 1 | Related to value or pricing, but indirect. | Use the efficiency gains to deliver more features, reduce external dependencies are kill technical debt. AI is cheaper way to keep things... |
| Hybrid | 12 | 1 | Related to value or pricing, but indirect. | Look at it this way, if it’s a task that an AI can do, then it is really work you want to do? |
| Hybrid | 13 | 1 | Related to value or pricing, but indirect. | s=20)\] * A fox news guy asked what the government is doing about AI that will cause the death of everyone. This is the type of fear mong... |
| Hybrid | 14 | 1 | Related to value or pricing, but indirect. | The biggest edge I’ve seen isn’t a specific tool but using AI to remove small repetitive tasks (research, summaries, quick prototypes). |
| Hybrid | 15 | 1 | Related to value or pricing, but indirect. | usage-based sounds logical until you realize most users have no idea how much they will use it and they churn before they even get value... |
| Hybrid | 16 | 1 | Related to value or pricing, but indirect. | the pricing problem with AI features comes down to one thing: are you pricing on COST or VALUE? |
| Hybrid | 17 | 0 | Off-topic for paying. | AI can do that as well though. |
| Hybrid | 18 | 0 | Off-topic for paying. | Of course someone will pay for open source. That’s already what a lot AI companies today are anyway. |
| Hybrid | 19 | 1 | Related to value or pricing, but indirect. | AI is an advanced tool, until you have an understanding of how to use an editor and write a working piece of code, how are you going to k... |
| Hybrid | 20 | 1 | Related to value or pricing, but indirect. | Reminder that AI can be a good tool for honest professionals and is not inherently bad. |

### What do users think about Claude compared to GPT?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid retrieves far more direct Claude-versus-GPT opinions.
- BM25 diagnostics: mode=lexical, response_ms=51.6, lexical_hits=17, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3948.13, lexical_hits=17, vector_hits=198, fused_hits=213, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 8 vs Hybrid 35 (delta +27)
- Relevant@20: BM25 8 vs Hybrid 19 (delta +11)
- Highly relevant@20: BM25 0 vs Hybrid 16 (delta +16)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 1, '6-10': 3, '11-20': 4} | Hybrid {'1-5': 10, '6-10': 8, '11-20': 17}
- Relevant overlap: 0 shared, 19 hybrid-only, 8 BM25-only
- Hybrid-only relevant examples: r16: But Claude in excel is legitimately good, as is Claude code.; r13: ChatGPT is still the generalist king, but it's been behind on coding since Claude 3.7 came out. Claude 4 is still bet...; r6: ChatGPT tends to give better SEO structure and creative suggestions, while Claude is decent for longer text editing.
- BM25-only relevant examples: r13: I can ask: "what are the top 10 users by order count?" and Claude just queries my dev database and answers.; r7: I can say definitively - that thanks to people pushing SEO myths - LLMs are more clueless about SEO than ever before....; r11: I still have open-ended questions, but I’m curious, what do you think?! Is this all crazy talk? Can we realistically...
- Spot checks: Hybrid repeatedly compares Claude and GPT head to head.; BM25 gets a few comparison hits, but drifts into unrelated material.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Related to Claude or GPT, but indirect. | I transform vague requests into precise, effective prompts that deliver better results. **What I need to know:** - **Target AI:** ChatGPT... |
| BM25 | 2 | 0 | Not a Claude-vs-GPT comparison. | What do we leave for those that have no idea about it at all? |
| BM25 | 3 | 0 | Not a Claude-vs-GPT comparison. | While it's still in early stages, it's functional and might help others in similar situations. Here's what it looks like: https://i.redd.... |
| BM25 | 4 | 0 | Not a Claude-vs-GPT comparison. | s=20)\] * A fox news guy asked what the government is doing about AI that will cause the death of everyone. |
| BM25 | 5 | 0 | Not a Claude-vs-GPT comparison. | Have yall compared LLMs for SEO work/assistance?. I've been a longtime ChatGPT user and recently am testing Claude. |
| BM25 | 6 | 1 | Related to Claude or GPT, but indirect. | Use 'clip list' to see available clips → Agent knows to list clips first ``` Technique 1 (help) solves "what can I do?" Technique 2 (erro... |
| BM25 | 7 | 1 | Related to Claude or GPT, but indirect. | I can say definitively - that thanks to people pushing SEO myths - LLMs are more clueless about SEO than ever before. Here's the output f... |
| BM25 | 8 | 1 | Related to Claude or GPT, but indirect. | Switching-intent prompts ("I want to move away from X, what should I use?") produced the highest median fragmentation a 56% provider spre... |
| BM25 | 9 | 0 | Not a Claude-vs-GPT comparison. | The LLM in use is Qwen3.5 9B Q4\_K\_M (parameters: Top-k = 40, top-p: 0.95, min-p = 0.01, temperature = 1.0, no thinking/reasoning). Qwen... |
| BM25 | 10 | 0 | Not a Claude-vs-GPT comparison. | more on the getting paid part below now. building a community from zero is its own kind of hell. i've been reading about how other platfo... |
| BM25 | 11 | 1 | Related to Claude or GPT, but indirect. | I still have open-ended questions, but I’m curious, what do you think?! Is this all crazy talk? Can we realistically envision an OS revol... |
| BM25 | 12 | 0 | Not a Claude-vs-GPT comparison. | BUT unfortunately, you need to look carefully at what vendors are really doing because some are only looking at subject lines, which limi... |
| BM25 | 13 | 1 | Related to Claude or GPT, but indirect. | I can ask: "what are the top 10 users by order count?" and Claude just queries my dev database and answers. |
| BM25 | 14 | 0 | Not a Claude-vs-GPT comparison. | Because if you do that, opportunities will come. About your situation (financial pressure, family, etc.) |
| BM25 | 15 | 1 | Related to Claude or GPT, but indirect. | 😂 I recently learned about this terminology, just as I was exceeding the $1,000 psychological threshold on Claude Code. |
| BM25 | 16 | 1 | Related to Claude or GPT, but indirect. | Questions about how Tiiny AI is 'doing it' So, I recently found out about Tiiny AI, which is a small 1600 dollar computer with fast RAM a... |
| BM25 | 17 | 0 | Not a Claude-vs-GPT comparison. | Next time the security panic button gets hit, pause and think about the cost vs. benefit. Is the payoff huge? |
| Hybrid | 1 | 2 | Directly compares Claude and GPT. | Claude |
| Hybrid | 2 | 2 | Directly compares Claude and GPT. | Claude is the best |
| Hybrid | 3 | 2 | Directly compares Claude and GPT. | Same. For coding Claude is better than GPT. |
| Hybrid | 4 | 2 | Directly compares Claude and GPT. | Claude definitely seems to be more geared towards code, and it seems to do better with some code over others. |
| Hybrid | 5 | 2 | Directly compares Claude and GPT. | Try Claude. |
| Hybrid | 6 | 2 | Directly compares Claude and GPT. | ChatGPT tends to give better SEO structure and creative suggestions, while Claude is decent for longer text editing. |
| Hybrid | 7 | 2 | Directly compares Claude and GPT. | GPT-5 is a massive improvement compared to its previous iterations. It's also better than Claude. |
| Hybrid | 8 | 2 | Directly compares Claude and GPT. | Have yall compared LLMs for SEO work/assistance?. I've been a longtime ChatGPT user and recently am testing Claude. |
| Hybrid | 9 | 1 | Related to Claude or GPT, but indirect. | Gemini is about as good as ChatGPT currently. I'm subbed to Claude and Gemini. |
| Hybrid | 10 | 1 | Related to Claude or GPT, but indirect. | I asked Claude to search for user experiences considering Altman hyped it with AGI feel & Oppenheimer references and this was the respons... |
| Hybrid | 11 | 2 | Directly compares Claude and GPT. | EDIT: after trying chatgpt 5, i like claude more. ChatGPT 5 was doing so crazy shit and churning and churning, it can't be trusted. |
| Hybrid | 12 | 2 | Directly compares Claude and GPT. | Claude is better at coding diagnostics (sometimes) but yeah ChatGPT is overall better in this line of work for a lot |
| Hybrid | 13 | 2 | Directly compares Claude and GPT. | ChatGPT is still the generalist king, but it's been behind on coding since Claude 3.7 came out. Claude 4 is still better than GPT 5 (from... |
| Hybrid | 14 | 2 | Directly compares Claude and GPT. | Claude is overly censored and feels like it was created for people living in a police state, it's only really good for coding. |
| Hybrid | 15 | 2 | Directly compares Claude and GPT. | Consistently going back a couple of years now I have just always noticed that Claude gives more useful responses no matter what I’m doing. |
| Hybrid | 16 | 2 | Directly compares Claude and GPT. | But Claude in excel is legitimately good, as is Claude code. |
| Hybrid | 17 | 1 | Related to Claude or GPT, but indirect. | I think OpenAI is more generous with usage limits in paid tier while I run out of Claude pro usage limits pretty fast. |
| Hybrid | 18 | 2 | Directly compares Claude and GPT. | We use Claude with Cline and a custom wrapper at my company and it has increased my productivity so much. |
| Hybrid | 19 | 2 | Directly compares Claude and GPT. | Claude is a best and you're not limited (unless you run out of tokens/prompts) Hmu if you need a hand optimising your site with Claude..:) |
| Hybrid | 20 | 0 | Not a Claude-vs-GPT comparison. | this post sponsored by claude |

### Is Gemini better than ChatGPT?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid better matches the Gemini-vs-ChatGPT comparison intent.
- BM25 diagnostics: mode=lexical, response_ms=36.84, lexical_hits=14, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2079.24, lexical_hits=14, vector_hits=200, fused_hits=214, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 8 vs Hybrid 24 (delta +16)
- Relevant@20: BM25 6 vs Hybrid 14 (delta +8)
- Highly relevant@20: BM25 2 vs Hybrid 10 (delta +8)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 5, '6-10': 2, '11-20': 1} | Hybrid {'1-5': 10, '6-10': 9, '11-20': 5}
- Relevant overlap: 0 shared, 14 hybrid-only, 6 BM25-only
- Hybrid-only relevant examples: r10: Am I just crazy or is ChatGPT way better than this and Google is just slacking?; r6: ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. Easy to...; r3: Claude is good at coding and planning, not so much in general knowledge. Gemini is about as good as ChatGPT currently...
- BM25-only relevant examples: r10: (i will not promote) i'm a vibe coder whose background is in semiconductor hardware. i started this whole journey wit...; r4: FAQs and content comprehensiveness help but only if the content is genuinely the best answer to a specific question....; r2: I find gemini 2.5 pro so much better than claude any model
- Spot checks: Hybrid surfaces explicit comparison judgments near the top.; BM25 has some direct hits, but fewer and less consistently.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly compares Gemini and ChatGPT. | In fact, I swear current Gemini is already better than this? Maybe not for calling but if you just take a photo of the broken brakes tell... |
| BM25 | 2 | 2 | Directly compares Gemini and ChatGPT. | I find gemini 2.5 pro so much better than claude any model |
| BM25 | 3 | 0 | Not a Gemini-vs-ChatGPT comparison. | I have broken it down into 6 steps for the AI (lemmatization, recognizing different words with the same lemma, metadata, verb conjugation... |
| BM25 | 4 | 1 | Related to Gemini or ChatGPT, but indirect. | FAQs and content comprehensiveness help but only if the content is genuinely the best answer to a specific question. LLMs are better at d... |
| BM25 | 5 | 0 | Not a Gemini-vs-ChatGPT comparison. | 👆🏻agreed. Better fees than Gemini or Coinbase right off the bat for a new account |
| BM25 | 6 | 0 | Not a Gemini-vs-ChatGPT comparison. | Even better, Gemini Advanced Trader mode has even lower fee than CB |
| BM25 | 7 | 1 | Related to Gemini or ChatGPT, but indirect. | You chain them together, and you get a better result than any one model gives you alone. |
| BM25 | 8 | 0 | Not a Gemini-vs-ChatGPT comparison. | My DCA is from digital mining, there’s better tax-free options I’ve become aware of like abundant mines, which is the next goal. |
| BM25 | 9 | 0 | Not a Gemini-vs-ChatGPT comparison. | Everyday it blows my mind how much better it is than searching Google. |
| BM25 | 10 | 1 | Related to Gemini or ChatGPT, but indirect. | (i will not promote) i'm a vibe coder whose background is in semiconductor hardware. i started this whole journey with zero CS knowledge,... |
| BM25 | 11 | 0 | Not a Gemini-vs-ChatGPT comparison. | So you need to be fast and preplanned rather than build first and then find out monitization later. |
| BM25 | 12 | 1 | Related to Gemini or ChatGPT, but indirect. | I'm not smart enough to understand this, so I asked Gemini to ELI5: The Short Version: Imagine you built a really fast toy race car. |
| BM25 | 13 | 0 | Not a Gemini-vs-ChatGPT comparison. | You need to write better information than him, and the others. But they STILL WON'T FIND YOU if you don't include the keywords in their s... |
| BM25 | 14 | 0 | Not a Gemini-vs-ChatGPT comparison. | Drop any executable script into a folder, Panther registers it as a callable tool automatically. I'm not saying it's better than OpenClaw... |
| Hybrid | 1 | 2 | Directly compares Gemini and ChatGPT. | I’m sorry but I’m not buying that Gemini is nearly as accurate as ChatGPT. Clearly GPT has better reasoning and can essentially process c... |
| Hybrid | 2 | 2 | Directly compares Gemini and ChatGPT. | https://terminal.eli5a.com does it better and more accurate. Their latest research paper shows it beat Gemini & ChatGPT with little to no... |
| Hybrid | 3 | 2 | Directly compares Gemini and ChatGPT. | Claude is good at coding and planning, not so much in general knowledge. Gemini is about as good as ChatGPT currently. I'm subbed to Clau... |
| Hybrid | 4 | 2 | Directly compares Gemini and ChatGPT. | It depends on the AI tool. Gemini uses google. Chat gpt uses proprietary and Microsoft data. |
| Hybrid | 5 | 2 | Directly compares Gemini and ChatGPT. | Yes, he used Tynker and CodeMonkey to learn some JS (functions, arrays, etc) prior to building this game. Gemini is Google's version of C... |
| Hybrid | 6 | 2 | Directly compares Gemini and ChatGPT. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. Easy to believe it unknowin... |
| Hybrid | 7 | 1 | Related to Gemini or ChatGPT, but indirect. | 👆🏻agreed. Better fees than Gemini or Coinbase right off the bat for a new account |
| Hybrid | 8 | 2 | Directly compares Gemini and ChatGPT. | That's what I mean - you do realize Gemini is now sending 66% of the traffic ChatGPT is which declined by about a third since January 1? |
| Hybrid | 9 | 2 | Directly compares Gemini and ChatGPT. | Ngl, I’ve recently started talking to Gemini because it gets straight to the point. All that extra shit is unnecessary and they need to f... |
| Hybrid | 10 | 2 | Directly compares Gemini and ChatGPT. | Am I just crazy or is ChatGPT way better than this and Google is just slacking? |
| Hybrid | 11 | 1 | Related to Gemini or ChatGPT, but indirect. | It was only the Bing Chat version that was mentally unstable. ChatGPT hosted by OpenAI is fine. |
| Hybrid | 12 | 2 | Directly compares Gemini and ChatGPT. | Right, but ChatGPT gives a better result, and can be personalized. Why always opt for Google when there is a better tool for the job? |
| Hybrid | 13 | 0 | Not a Gemini-vs-ChatGPT comparison. | Ask ChatGPT |
| Hybrid | 14 | 1 | Related to Gemini or ChatGPT, but indirect. | Some users appreciate the convenience of being able to get answers to their questions quickly, while others enjoy the novelty of interact... |
| Hybrid | 15 | 1 | Related to Gemini or ChatGPT, but indirect. | I think it's important to note that ChatGPT has only been around for just under 3 years total. That's pretty incredible for a frontier ne... |
| Hybrid | 16 | 0 | Not a Gemini-vs-ChatGPT comparison. | I don’t use google anymore ChatGPT is much better. |
| Hybrid | 17 | 0 | Not a Gemini-vs-ChatGPT comparison. | Or how to try to prompt it to fix it let alone know when it's so off the rails that it's not useful anymore. I've broken Gemini and ChatG... |
| Hybrid | 18 | 0 | Not a Gemini-vs-ChatGPT comparison. | > Might be helpful for Bing or Yandex (which could *maybe* help with some AI visibility), but that's about it. Does nothing for Google AF... |
| Hybrid | 19 | 0 | Not a Gemini-vs-ChatGPT comparison. | Lol man I feel like my relationship with ChatGPT is way different https://preview.redd.it/pt40yzcop35f1.png?width=1024&format=png&auto=we... |
| Hybrid | 20 | 0 | Not a Gemini-vs-ChatGPT comparison. | I think you guys are just not very good and reading and can't tell that I was agreeing. >The things I use ChatGPT for, it does a fantasti... |

### Do AI models make too many mistakes?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid is stronger on mistakes, errors, and the need for checking.
- BM25 diagnostics: mode=lexical, response_ms=67.36, lexical_hits=82, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3122.31, lexical_hits=82, vector_hits=199, fused_hits=280, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 11 vs Hybrid 22 (delta +11)
- Relevant@20: BM25 9 vs Hybrid 15 (delta +6)
- Highly relevant@20: BM25 2 vs Hybrid 7 (delta +5)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 3, '6-10': 1, '11-20': 7} | Hybrid {'1-5': 8, '6-10': 6, '11-20': 8}
- Relevant overlap: 0 shared, 15 hybrid-only, 9 BM25-only
- Hybrid-only relevant examples: r11: AI can be right.; r7: AI can fix small bugs and small changes given a specific architecture and coding style provided.; r2: AI is full of mistakes, it’s helpful but you need to know what the fuck you’re doing do you don’t commit some shit co...
- BM25-only relevant examples: r12: As a programmer passionate about the profession, I want to push maintainability *all* the way to maximum. I am not pa...; r1: Google makes damn good AI, Google cannot make a fully sentient digital being.; r4: I fucked it up that time because I was too young to notice, but not again. **TL-DR:** AI is comparable to the interne...
- Spot checks: Hybrid keeps mistake-focused language near the top.; BM25 is relevant but more diffuse.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Related to mistakes, but indirect. | Google makes damn good AI, Google cannot make a fully sentient digital being. |
| BM25 | 2 | 0 | Not about mistakes. | I had a person working in my team, and we were training a model in colab. He just wanted to do the training part himself (probably for li... |
| BM25 | 3 | 0 | Not about mistakes. | I tried feeding that exact same system prompt Sonnet 4.5 to Qwen3.5 27B and it didn't change how it acted, so I ruled out the system prom... |
| BM25 | 4 | 2 | Directly addresses AI mistakes. | I fucked it up that time because I was too young to notice, but not again. **TL-DR:** AI is comparable to the internet first and smartpho... |
| BM25 | 5 | 0 | Not about mistakes. | s=20)\] * Build financial models with AI. Lots of jobs in finance at risk too \[[Link](https://twitter.com/ryankishore_/status/1641553735... |
| BM25 | 6 | 0 | Not about mistakes. | He orders the AI team to make Grok more right wing and this is what happens. |
| BM25 | 7 | 0 | Not about mistakes. | Here's what it looks like: https://i.redd.it/v6j508rxkjhe1.gif [https://github.com/OpenHealthForAll/open-health](https://github.com/OpenH... |
| BM25 | 8 | 1 | Related to mistakes, but indirect. | Yeah, tried using Claude code/4omini the other day for writing simple ass fucking oauth app and it made the whole codebase a steaming pil... |
| BM25 | 9 | 0 | Not about mistakes. | When we finally give them a compilation, while they do ban some of the reviews, many are not removed (https://imgur.com/a/ogbaTo5). we've... |
| BM25 | 10 | 0 | Not about mistakes. | Unlikely to happen though, because way too many developers are still financially trapped, despite the wages. |
| BM25 | 11 | 1 | Related to mistakes, but indirect. | If your into AI, if your curious about what it can do, how easily you can find quality information using it to find stuff for you online,... |
| BM25 | 12 | 1 | Related to mistakes, but indirect. | As a programmer passionate about the profession, I want to push maintainability *all* the way to maximum. I am not paid to do that becaus... |
| BM25 | 13 | 0 | Not about mistakes. | Only a fool would underestimate Elon Musk too. Grok is super powerful, it also has vision models, his Twitter advantage, it's own video m... |
| BM25 | 14 | 1 | Related to mistakes, but indirect. | To test the global vs. local optimization of the model. My hypothesis is also that this wouldn't be well suited for memorizing facts, but... |
| BM25 | 15 | 0 | Not about mistakes. | Here's a set of 20 tweet-style lines that subtly suggest an AI-related release—keeping it fun, clever, and not too on-the-nose: --- 1. |
| BM25 | 16 | 2 | Directly addresses AI mistakes. | That black box opacity is a familiar challenge in AI. Language models, by their very nature, excel at bringing together contributions fro... |
| BM25 | 17 | 0 | Not about mistakes. | That litellm supply chain attack is a wake up call. checked my deps and found 3 packages pulling it in So if you missed it, litellm (the... |
| BM25 | 18 | 0 | Not about mistakes. | You know how even if you're the bottom 1% earner in the US you're top 1% in the world? It's like that too, with intelligence/education an... |
| BM25 | 19 | 1 | Related to mistakes, but indirect. | 🚮 Imagine being so lazy and uninspired that you need AI to do your flirting for you. 😬🙈 Online dating is already a minefield, but now we... |
| BM25 | 20 | 1 | Related to mistakes, but indirect. | Most people here will tell you to just ask AI - and it'll do a halfway decent job, but it will just make some shit up or be wrong in many... |
| Hybrid | 1 | 2 | Directly addresses AI mistakes. | Yes, I don’t think AI makes as much errors with Product work. I meant purely from the engineering point of view - AI has major problems. |
| Hybrid | 2 | 2 | Directly addresses AI mistakes. | AI is full of mistakes, it’s helpful but you need to know what the fuck you’re doing do you don’t commit some shit code and take down the... |
| Hybrid | 3 | 1 | Related to mistakes, but indirect. | Because you learn by figuring things out, making mistakes, and correcting them. If AI does it for you, you won’t look deep enough into ho... |
| Hybrid | 4 | 2 | Directly addresses AI mistakes. | It makes mistakes, but like it or not its not going anywhere, and like with anything using AI effectively is a skill in itself. |
| Hybrid | 5 | 1 | Related to mistakes, but indirect. | Well if AI says so… |
| Hybrid | 6 | 1 | Related to mistakes, but indirect. | Yes, I find often times even the best AI still needs guidance, but you won’t know what needs to be tweaked if you have no idea what it’s... |
| Hybrid | 7 | 2 | Directly addresses AI mistakes. | AI can fix small bugs and small changes given a specific architecture and coding style provided. |
| Hybrid | 8 | 2 | Directly addresses AI mistakes. | The less you know about a topic, the harder it will be for you to spot the AI's mistakes, even when you do check its sources. |
| Hybrid | 9 | 1 | Related to mistakes, but indirect. | I'm not saying that means AI will replace devs anytime soon but it's silly to pretend cutting your errors in half isn't a huge improvement. |
| Hybrid | 10 | 0 | Not about mistakes. | Agreed. AI isn’t perfect and it occasionally is wrong, but google has also lead me to many posts that were wrong |
| Hybrid | 11 | 1 | Related to mistakes, but indirect. | AI can be right. |
| Hybrid | 12 | 1 | Related to mistakes, but indirect. | But the majority of people using AI are not making these mistakes: > (funny thing, it didn't even connect to colab, and he just gave the... |
| Hybrid | 13 | 1 | Related to mistakes, but indirect. | AI makes horrible, messy code that as a program grows in complexity will lead to bugs that it cannot fix. |
| Hybrid | 14 | 1 | Related to mistakes, but indirect. | AI is like a self-driving car. It does awesome on a new well-built road, and no weird exceptions show up. once it hits something it's not... |
| Hybrid | 15 | 0 | Not about mistakes. | I mean, if they don’t teach you how to use AI you’re all gonna use it anyway. They might as well prepare you for what kind of mistakes it... |
| Hybrid | 16 | 0 | Not about mistakes. | I think this guy wasn’t even using AI properly. The mistakes you mentioned in your post could be easily avoided with today’s AI models. |
| Hybrid | 17 | 2 | Directly addresses AI mistakes. | You learn from experience and grow. The AI only gets better if its model does. |
| Hybrid | 18 | 0 | Not about mistakes. | the ai model is competent, your team member was not, there is a difference - you wouldn't have this issue w/ an ai agent |
| Hybrid | 19 | 0 | Not about mistakes. | In the best case, your AI will be only as good as people programming/training it. |
| Hybrid | 20 | 2 | Directly addresses AI mistakes. | We do not know the impact of using AI/LLMs on our minds and cognition, and its perfectly acceptable to be apprehensive of using them too... |

### Are people satisfied with current AI technology?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid better reflects satisfaction and dissatisfaction with current AI.
- BM25 diagnostics: mode=lexical, response_ms=48.37, lexical_hits=73, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2535.05, lexical_hits=73, vector_hits=198, fused_hits=263, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 15 vs Hybrid 19 (delta +4)
- Relevant@20: BM25 12 vs Hybrid 15 (delta +3)
- Highly relevant@20: BM25 3 vs Hybrid 4 (delta +1)
- First relevant rank: BM25 1 | Hybrid 2
- Band totals: BM25 {'1-5': 5, '6-10': 3, '11-20': 7} | Hybrid {'1-5': 5, '6-10': 7, '11-20': 7}
- Relevant overlap: 0 shared, 15 hybrid-only, 12 BM25-only
- Hybrid-only relevant examples: r15: Agreed. Eventually people will understand AI well enough, and it will improve enough, that it will be a useful tool f...; r5: AI can be right.; r8: AI is a powerful tool that IF utilized properly, can alleviate many of the conditions and afflictions humanity suffer...
- BM25-only relevant examples: r3: AI making my job so much harder and fighting every decision I make — I’ve been an IT manager for a long time, and I’v...; r10: At least at my current role the CEO is fully buying into the AI hype train and investing heavily into AI systems.; r4: EDIT: Some people have argued that AI is a big reason as to why Medium is going under...
- Spot checks: Hybrid surfaces sentiment about current AI earlier.; BM25 mixes in broader market commentary.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Related to current AI sentiment, but indirect. | It's funny. People acting like Deepseek is any different to any current AI programs regarding censorship. |
| BM25 | 2 | 1 | Related to current AI sentiment, but indirect. | People need to chill with this AI is sentient crap, the current models used for nlp are just attempting to string words together with the... |
| BM25 | 3 | 2 | Directly addresses satisfaction with current AI. | AI making my job so much harder and fighting every decision I make — I’ve been an IT manager for a long time, and I’ve seen every "game-c... |
| BM25 | 4 | 1 | Related to current AI sentiment, but indirect. | EDIT: Some people have argued that AI is a big reason as to why Medium is going under... |
| BM25 | 5 | 0 | Not about satisfaction. | All of those play some part of the story. But here's what people tend to overlook: no one **ever** wanted junior engineers. |
| BM25 | 6 | 0 | Not about satisfaction. | Because we banned additional people using severe insults and slurs towards game staff, the mob got bigger and continued for months. |
| BM25 | 7 | 1 | Related to current AI sentiment, but indirect. | In theory, the more current jobs AI is able to do, the cheaper goods should become, similar to how music is essentially free online now. |
| BM25 | 8 | 1 | Related to current AI sentiment, but indirect. | If the CEO dreamers move away from AI, or people find some easier way to do it, and people finally put crypto to sleep, life is going to... |
| BM25 | 9 | 0 | Not about satisfaction. | People will want to use AI to control other people. |
| BM25 | 10 | 1 | Related to current AI sentiment, but indirect. | At least at my current role the CEO is fully buying into the AI hype train and investing heavily into AI systems. |
| BM25 | 11 | 0 | Not about satisfaction. | We have processes that are concrete and Cannot Be Changed. Right now we see AI only in our fringes because there simply isn't a gap we ne... |
| BM25 | 12 | 0 | Not about satisfaction. | Even before AI, it was a big problem with people hiring professionals to interview for them. |
| BM25 | 13 | 0 | Not about satisfaction. | So now, taking this to software development, data science, AI/ML, etc. What are the things that AI is going to probably be really good at? |
| BM25 | 14 | 1 | Related to current AI sentiment, but indirect. | I’ve been thinking a lot about the current wave of AI devtool startups (especially recent YC batches), who are targeting the audience who... |
| BM25 | 15 | 1 | Related to current AI sentiment, but indirect. | Like, this is what I want to see AI used for- to actually improve people’s lives and be more independent and solve medical issues. |
| BM25 | 16 | 0 | Not about satisfaction. | (source: https://projects.oregonlive.com/maps/earthquakes/buildings/ ) ... significantly advanced AI isn't some easy, quick or magical fi... |
| BM25 | 17 | 0 | Not about satisfaction. | I will not promote I’m trying to understand where design tends to become a problem inside startups and help them solve it. I’m currently... |
| BM25 | 18 | 2 | Directly addresses satisfaction with current AI. | No, it sounds like the choice has already been made but they're just looking for an easier excuse to throw people out. Our organisation i... |
| BM25 | 19 | 2 | Directly addresses satisfaction with current AI. | Even if you are smart enough to not blindly rubberstamp AI code, a lot of other people will. The current group of AIs don't do clean stru... |
| BM25 | 20 | 1 | Related to current AI sentiment, but indirect. | I'm currently building a small AI assistant that helps manage Google Calendar scheduling and email threads. |
| Hybrid | 1 | 0 | Not about satisfaction. | AI? |
| Hybrid | 2 | 1 | Related to current AI sentiment, but indirect. | is this AI its getting better |
| Hybrid | 3 | 1 | Related to current AI sentiment, but indirect. | I've had a lot of fun playing with AI and code generation since it came out, and I'm currently doing research on how we can best use AI t... |
| Hybrid | 4 | 2 | Directly addresses satisfaction with current AI. | but workers who use AI are less productive than workers who do. This is different from other emerging technologies, which were actually u... |
| Hybrid | 5 | 1 | Related to current AI sentiment, but indirect. | AI can be right. |
| Hybrid | 6 | 1 | Related to current AI sentiment, but indirect. | I'm also tired of seeing "toilet now with AI" for whatever reason. When it comes to copyright I think that nothing should have it but a b... |
| Hybrid | 7 | 2 | Directly addresses satisfaction with current AI. | AI will not stop being better and better compared to humans who all are different but all have limits. |
| Hybrid | 8 | 2 | Directly addresses satisfaction with current AI. | AI is a powerful tool that IF utilized properly, can alleviate many of the conditions and afflictions humanity suffer from. |
| Hybrid | 9 | 2 | Directly addresses satisfaction with current AI. | I think current AI is more powerful than a "faster google search". |
| Hybrid | 10 | 0 | Not about satisfaction. | AI, need I say more? |
| Hybrid | 11 | 1 | Related to current AI sentiment, but indirect. | Even the best ai does this. It doesn't have to be humans or ai but many people see it that way. |
| Hybrid | 12 | 0 | Not about satisfaction. | Did the AI like it |
| Hybrid | 13 | 0 | Not about satisfaction. | AI making my job so much harder and fighting every decision I make — I’ve been an IT manager for a long time, and I’ve seen every "game-c... |
| Hybrid | 14 | 0 | Not about satisfaction. | Like, this is what I want to see AI used for- to actually improve people’s lives and be more independent and solve medical issues. |
| Hybrid | 15 | 1 | Related to current AI sentiment, but indirect. | Agreed. Eventually people will understand AI well enough, and it will improve enough, that it will be a useful tool for people who can us... |
| Hybrid | 16 | 1 | Related to current AI sentiment, but indirect. | The big issue with the people using AI is when you question their methods, they ask AI how to resond to the criticism. |
| Hybrid | 17 | 1 | Related to current AI sentiment, but indirect. | AI is improving steadily every roughly 10 years, with "AI winters" in between. |
| Hybrid | 18 | 1 | Related to current AI sentiment, but indirect. | Not everyone is sick of hearing about AI; opinions vary widely. Some people find AI fascinating and are eager to learn more, while others... |
| Hybrid | 19 | 1 | Related to current AI sentiment, but indirect. | The last company I worked at was like that and everyone was very negative about AI. The current company I work at provides decent tools a... |
| Hybrid | 20 | 1 | Related to current AI sentiment, but indirect. | Ive honestly just had to completely cut AI out of my life. Im in a place right now where im not in a good mental for writing code (just d... |

### What frustrates users the most about AI chatbots?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid is much better on frustration language and user complaints.
- BM25 diagnostics: mode=lexical, response_ms=57.95, lexical_hits=40, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3235.48, lexical_hits=40, vector_hits=196, fused_hits=235, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 10 vs Hybrid 32 (delta +22)
- Relevant@20: BM25 9 vs Hybrid 20 (delta +11)
- Highly relevant@20: BM25 1 vs Hybrid 12 (delta +11)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 3, '6-10': 1, '11-20': 6} | Hybrid {'1-5': 9, '6-10': 7, '11-20': 16}
- Relevant overlap: 0 shared, 20 hybrid-only, 9 BM25-only
- Hybrid-only relevant examples: r20: "when people need support, they dont want to talk to a dumb ai bot that just says random useless things wasting every...; r1: >One thing that frustrates me in regards to getting involved in the generic AI conversations that you find around her...; r16: Except it's not what you wanted to say, and has now distracted you as you choose to read what it "said" and then lose...
- BM25-only relevant examples: r1: "Why can't YOU just ASK ME what you need to know?" I typed in frustration. Wait.; r2: **Person:** "AI is going to replace us! It can literally code new features in seconds" **Me:** "Oh, what kind of feat...; r12: And that's when it clicked. most of my problems as a solo founder came down to the same thing: i couldn't see what ot...
- Spot checks: Hybrid stays close to actual chatbot frustration.; BM25 drifts into unrelated frustration examples.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | Related to chatbot frustration, but indirect. | "Why can't YOU just ASK ME what you need to know?" I typed in frustration. Wait. |
| BM25 | 2 | 1 | Related to chatbot frustration, but indirect. | **Person:** "AI is going to replace us! It can literally code new features in seconds" **Me:** "Oh, what kind of features are you talking... |
| BM25 | 3 | 0 | Not about chatbot frustration. | Be glad you're sure that most users are STILL human here and in most other places. |
| BM25 | 4 | 1 | Related to chatbot frustration, but indirect. | Changed diets, exercise routines, sleep schedules - nothing seemed to help. The most frustrating part wasn't just the lack of answers - i... |
| BM25 | 5 | 0 | Not about chatbot frustration. | FYI Everythings dangerous and guess what the most dangerous animal on this planet is humans. |
| BM25 | 6 | 0 | Not about chatbot frustration. | . - Base laptop is Framework 13, AMD 7640U, 64 GB RAM - Some have rounded displays, others not (User choice). About 25x Ryzen AI 7 350 sy... |
| BM25 | 7 | 0 | Not about chatbot frustration. | s=20)\] * A fox news guy asked what the government is doing about AI that will cause the death of everyone. |
| BM25 | 8 | 0 | Not about chatbot frustration. | While overall it's a minority of the Chinese playerbase (we had about 20k or so total, most people play from browser) that were disruptiv... |
| BM25 | 9 | 1 | Related to chatbot frustration, but indirect. | I honestly can't decide what's more frustrating: that a company is selling the idea of employees sending AI slop *to their bosses* as a b... |
| BM25 | 10 | 0 | Not about chatbot frustration. | That's a massive visibility gap and most hotel teams have no idea it exists. Here's what seems to actually matter: **Bing indexation is c... |
| BM25 | 11 | 0 | Not about chatbot frustration. | This is the core philosophy of the *nix Agent: **don't invent a new tool interface. Take what Unix has proven over 50 years and hand it d... |
| BM25 | 12 | 2 | Directly addresses user frustrations with chatbots. | And that's when it clicked. most of my problems as a solo founder came down to the same thing: i couldn't see what other people were stru... |
| BM25 | 13 | 1 | Related to chatbot frustration, but indirect. | I want to warn others about a really frustrating experience I’ve just had with Hostinger. |
| BM25 | 14 | 1 | Related to chatbot frustration, but indirect. | Even when the product is simple, if the first interaction isn’t very clear people just leave instead of exploring. And I agree about AI-g... |
| BM25 | 15 | 1 | Related to chatbot frustration, but indirect. | The more useful question is what the moat actually is. For most software it was never the underlying technology anyway. |
| BM25 | 16 | 0 | Not about chatbot frustration. | Once a list filled up, users opted for a different gadget with a shorter list. |
| BM25 | 17 | 0 | Not about chatbot frustration. | The interesting thing is what it reveals about how unprepared the legal system is for AI agents acting on behalf of users. |
| BM25 | 18 | 0 | Not about chatbot frustration. | As you can see, I am already telling the LLM a lot about what is what and from when the information is and how to use it. * Do you have s... |
| BM25 | 19 | 0 | Not about chatbot frustration. | Even with some level of endpoint security and monitoring in place, the real issue feels more like visibility and context than just contro... |
| BM25 | 20 | 1 | Related to chatbot frustration, but indirect. | Foundation, technical SEO, content, and even AI search optimization (any AI)? SEO is not about publishing hygenie - and I understand why... |
| Hybrid | 1 | 2 | Directly addresses user frustrations with chatbots. | >One thing that frustrates me in regards to getting involved in the generic AI conversations that you find around here is how whoefully u... |
| Hybrid | 2 | 1 | Related to chatbot frustration, but indirect. | If you’re upset about people wasting energy with AI, you’re going to have a bad time. |
| Hybrid | 3 | 2 | Directly addresses user frustrations with chatbots. | My biggest gripe with AI is when people who are not well-versed in technology are allowed to make decisions concerning it. |
| Hybrid | 4 | 2 | Directly addresses user frustrations with chatbots. | This is a good read, I say that as somone who works exceptionally deep in the SWE AI space all day every day. One thing that frustrates m... |
| Hybrid | 5 | 2 | Directly addresses user frustrations with chatbots. | The big issue with the people using AI is when you question their methods, they ask AI how to resond to the criticism. |
| Hybrid | 6 | 1 | Related to chatbot frustration, but indirect. | Some users appreciate the convenience of being able to get answers to their questions quickly, while others enjoy the novelty of interact... |
| Hybrid | 7 | 1 | Related to chatbot frustration, but indirect. | Title: The ChatGPT Chronicles In a world where people increasingly relied on AI to make their lives easier, Jane, an avid Reddit user, de... |
| Hybrid | 8 | 2 | Directly addresses user frustrations with chatbots. | I hope you get a real human soon, because this level of friction isn’t “AI progress,” it’s just bad product design wrapped in hype. |
| Hybrid | 9 | 1 | Related to chatbot frustration, but indirect. | One of our solutions is endlessly marketing AI based integrations to us. I've been letting each one do the salespitch, just in case there... |
| Hybrid | 10 | 2 | Directly addresses user frustrations with chatbots. | I feel this in my soul man. Fuck that AI chatbot and fuck them for this bullshit. |
| Hybrid | 11 | 2 | Directly addresses user frustrations with chatbots. | I honestly hate AI assistants. Most of them can’t give me the info I need and I just end up wanting to talk to a person. |
| Hybrid | 12 | 1 | Related to chatbot frustration, but indirect. | Like they're more afraid of hurting my feelings than actually putting me in dangerous situations. Gotta dial in that AI personality to be... |
| Hybrid | 13 | 2 | Directly addresses user frustrations with chatbots. | Most AI is designed to please the user as opposed to give the best answer. |
| Hybrid | 14 | 2 | Directly addresses user frustrations with chatbots. | The fucking dick riding AI assistants do, especially Chat GPT is so goddamn irritating personally, and so goddamn dangerous. |
| Hybrid | 15 | 2 | Directly addresses user frustrations with chatbots. | Fuck Atlassian, and Fuck AI — This is a full on rant spilling out of the absolute trash heap that is now support in all areas, especially... |
| Hybrid | 16 | 1 | Related to chatbot frustration, but indirect. | Except it's not what you wanted to say, and has now distracted you as you choose to read what it "said" and then lose your train of thought. |
| Hybrid | 17 | 1 | Related to chatbot frustration, but indirect. | Plus the actual AI integration rarely adds value, and the meat of what a user might need to ask can just be scripted without a 3rd party... |
| Hybrid | 18 | 1 | Related to chatbot frustration, but indirect. | The one that annoys me the most is on Linked In where some bot posts 'insert tech job is over look what this AI tool just did' and I just... |
| Hybrid | 19 | 2 | Directly addresses user frustrations with chatbots. | This phenomenon made ELIZA surprisingly addictive because users, seeking meaning and connection, often projected their own thoughts and f... |
| Hybrid | 20 | 2 | Directly addresses user frustrations with chatbots. | "when people need support, they dont want to talk to a dumb ai bot that just says random useless things wasting everyones time |

### Do developers like using AI tools?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid better surfaces developer opinions on adopting AI tools.
- BM25 diagnostics: mode=lexical, response_ms=54.07, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2655.19, lexical_hits=100, vector_hits=199, fused_hits=290, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 22 vs Hybrid 32 (delta +10)
- Relevant@20: BM25 17 vs Hybrid 20 (delta +3)
- Highly relevant@20: BM25 5 vs Hybrid 12 (delta +7)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 6, '6-10': 4, '11-20': 12} | Hybrid {'1-5': 9, '6-10': 10, '11-20': 13}
- Relevant overlap: 0 shared, 20 hybrid-only, 17 BM25-only
- Hybrid-only relevant examples: r7: AI Coding Agents Are Quietly Changing How Software Gets Built AI coding agents are quickly becoming one of the most t...; r16: But I feel like they're gonna regret that in 5 - 10 years when they realize half the code AI poops out is junk.; r1: Developers who learn to use AI as a tool are actually more valuable right now, not less.
- BM25-only relevant examples: r18: After asking the teacher about this, I was informed that the rest of the class will be using vibe coding. I was told...; r11: Also some of y'all are getting really defensive: I use the best tools I have at my disposal because that's my job as...; r3: And it’s already producing results like this. I’ve been following AI developments, but watching it do my job in my co...
- Spot checks: Hybrid is packed with developer sentiment and adoption language.; BM25 is relevant but less consistent.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly addresses developers using AI tools. | You sure have heard it, it has been repeated countless times in the last few weeks, even from some luminaries of the development world: "... |
| BM25 | 2 | 2 | Directly addresses developers using AI tools. | This is how you start to “see” problems. If you really want to use AI, use it like a helper, not like a driver. |
| BM25 | 3 | 1 | Related to developer use, but indirect. | And it’s already producing results like this. I’ve been following AI developments, but watching it do my job in my codebase made everythi... |
| BM25 | 4 | 1 | Related to developer use, but indirect. | That’s a big deal, because a lot of people talk like AI is going to replace software engineers any day now. |
| BM25 | 5 | 0 | Not about developer adoption. | 'we're in this bizarre world where the best way to learn about llms... is to read papers by chinese companies. i do not think this is a g... |
| BM25 | 6 | 2 | Directly addresses developers using AI tools. | There was a brief window when AI was this mysterious new magical tech and every developer wanted to know what it could do and how it coul... |
| BM25 | 7 | 1 | Related to developer use, but indirect. | Nvidia CEO says "I don't love AI slop myself" after giving Resident Evil Requiem's Grace a DLSS 5 makeover that was swiftly labelled AI s... |
| BM25 | 8 | 0 | Not about developer adoption. | This feels more and more like "Twitter got away with it? Fuck it, let's do it too." |
| BM25 | 9 | 1 | Related to developer use, but indirect. | Microsoft adding RAR, 7z, Gz and more to the native ZIP extractor, and finally having it use more than 1 CPU core. — They're also adding... |
| BM25 | 10 | 0 | Not about developer adoption. | Everyone who is supporting the mass use of AI is quietly digging their own grave and I wish it was never invented. |
| BM25 | 11 | 1 | Related to developer use, but indirect. | Also some of y'all are getting really defensive: I use the best tools I have at my disposal because that's my job as a developer. |
| BM25 | 12 | 1 | Related to developer use, but indirect. | Be glad AI is something you use, but it hasn't taken over us like the internet and smartphones did, not yet. |
| BM25 | 13 | 1 | Related to developer use, but indirect. | Me: Nobody uses it this way, its more like a useful tool to get something like a structure for a text you need, but not for… AI users: *D... |
| BM25 | 14 | 1 | Related to developer use, but indirect. | Build literally anything using AI. Type in “a chatbot” and see what happens. |
| BM25 | 15 | 1 | Related to developer use, but indirect. | Nonetheless, one can't simply be a BA and use it, I still need to be a senior developer IMO to harness it correctly. |
| BM25 | 16 | 1 | Related to developer use, but indirect. | I just think gatekeeping useful tools is cringe. Here's the entire Lyra prompt: You are Lyra, a master-level AI prompt optimization speci... |
| BM25 | 17 | 1 | Related to developer use, but indirect. | The problem with AI is that it eliminates most of the roles that aspiring VAs would be using as stepping stones to higher profile roles l... |
| BM25 | 18 | 2 | Directly addresses developers using AI tools. | After asking the teacher about this, I was informed that the rest of the class will be using vibe coding. I was told that using AI for th... |
| BM25 | 19 | 1 | Related to developer use, but indirect. | Open source projects/tools vendor locking themselves to openai? PS1: This may look like a rant, but other opinions are welcome, I may be... |
| BM25 | 20 | 2 | Directly addresses developers using AI tools. | The remedy is simple: treat AI like a tutor. Ask it about concepts. But write your own code. |
| Hybrid | 1 | 2 | Directly addresses developers using AI tools. | Developers who learn to use AI as a tool are actually more valuable right now, not less. |
| Hybrid | 2 | 2 | Directly addresses developers using AI tools. | We're all using AI. The ones that aren't are choosing to work on hard mode and likely just costing their products money. |
| Hybrid | 3 | 2 | Directly addresses developers using AI tools. | It’s not about not investing in AI, it’s about how it’s used. If it improves tools and workflows, great. |
| Hybrid | 4 | 2 | Directly addresses developers using AI tools. | very true. i am a software developer and i heavily rely on these ai tools to work my way through tasks. having a sound understanding of w... |
| Hybrid | 5 | 1 | Related to developer use, but indirect. | You are spot on. I am a developer because I like solving those puzzles with code. |
| Hybrid | 6 | 2 | Directly addresses developers using AI tools. | This is how you start to “see” problems. If you really want to use AI, use it like a helper, not like a driver. |
| Hybrid | 7 | 2 | Directly addresses developers using AI tools. | AI Coding Agents Are Quietly Changing How Software Gets Built AI coding agents are quickly becoming one of the most transformative tools... |
| Hybrid | 8 | 2 | Directly addresses developers using AI tools. | honestly the devs who learn to work with AI are going to be more valuable not less. I wasn't even a traditional developer and I built a w... |
| Hybrid | 9 | 2 | Directly addresses developers using AI tools. | I'm actually happy to hear about this. AI tools are a part of nearly all development teams now, and they aren't going away. |
| Hybrid | 10 | 2 | Directly addresses developers using AI tools. | In my experience, the worse the dev the more reliant on AI as a crutch for everything. As someone who enjoys writing code I get annoyed b... |
| Hybrid | 11 | 2 | Directly addresses developers using AI tools. | I really hope not, because if the next generation of developers genuinely can't write code independently of some AI tool, then their skil... |
| Hybrid | 12 | 2 | Directly addresses developers using AI tools. | Think of AI more like a helper for reading and exploring code, not a replacement for understanding it. |
| Hybrid | 13 | 1 | Related to developer use, but indirect. | Yeah many developers these days think all companies are green fielding new projects and creating new features every week. |
| Hybrid | 14 | 1 | Related to developer use, but indirect. | The pace of progress in AI is incredible, and it's becoming a very useful tool, even for experienced developers. |
| Hybrid | 15 | 2 | Directly addresses developers using AI tools. | If something breaks or behaves strangely, you still need enough context to know whether the AI suggestion makes sense or not. Most devs I... |
| Hybrid | 16 | 1 | Related to developer use, but indirect. | But I feel like they're gonna regret that in 5 - 10 years when they realize half the code AI poops out is junk. |
| Hybrid | 17 | 1 | Related to developer use, but indirect. | Using AI to write your code is like getting into management. |
| Hybrid | 18 | 1 | Related to developer use, but indirect. | Look for nuanced analysis of what it is actually good at, and then see what you can do as a human developer that AI struggles with. |
| Hybrid | 19 | 1 | Related to developer use, but indirect. | That’s a big deal, because a lot of people talk like AI is going to replace software engineers any day now. |
| Hybrid | 20 | 1 | Related to developer use, but indirect. | I hate this argument. Will it replace us in short/mid term? No. But it is an excellent tool with capabilities to make developers more pro... |

### Is AI helping productivity or making things worse?

- Category: `semantic`
- Winner: `hybrid`
- Rationale: Hybrid best captures the productivity-vs-harm tradeoff.
- BM25 diagnostics: mode=lexical, response_ms=68.54, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3583.63, lexical_hits=100, vector_hits=198, fused_hits=293, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 16 vs Hybrid 35 (delta +19)
- Relevant@20: BM25 12 vs Hybrid 20 (delta +8)
- Highly relevant@20: BM25 4 vs Hybrid 15 (delta +11)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 3, '6-10': 4, '11-20': 9} | Hybrid {'1-5': 10, '6-10': 9, '11-20': 16}
- Relevant overlap: 0 shared, 20 hybrid-only, 12 BM25-only
- Hybrid-only relevant examples: r1: ai helps most with speed on small repetitive tasks. research summaries, rough drafts, quick prototypes. the gap is st...; r3: AI is a real thing you can use now to increase your productivity.; r12: AI is just a tool. It can help junior employees do their work faster but replace hmmm... not really
- BM25-only relevant examples: r16: "I will not promote" I spend my week reviewing inbound pitch decks for a syndicate out in Bellevue, mostly focused on...; r7: >To make things worse, users are installing AI agents on their work computers, despite some of us saying "absolutely...; r17: And, as you've already observed with your peers, letting the AI spit something out you can't understand and putting i...
- Spot checks: Hybrid stays closely aligned with the question across the whole ranking.; BM25 is relevant but less focused.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | Directly addresses productivity effects. | So yeah, the tech is cool and it’ll keep getting better, but the progress isn’t revolutionary anymore. My guess is AI will keep being a h... |
| BM25 | 2 | 0 | Not about productivity effects. | 20+ years in tech, and here's the one thing I'd tell every new programmer — I've written production code in everything from C to Rust to... |
| BM25 | 3 | 0 | Not about productivity effects. | I am actually a person who is very willing to explain things to others and it makes me feel good. However, he didn't even ask for help, a... |
| BM25 | 4 | 1 | Related to productivity, but indirect. | Langchain makes it very easy for anyone to build AI powered apps. |
| BM25 | 5 | 0 | Not about productivity effects. | I think one of the things I struggle the most with is feeling like I don’t know my codebase anymore. |
| BM25 | 6 | 1 | Related to productivity, but indirect. | You cant really say humans are social creatures who read tons of signals from one another, which is true, and also say that wfh doesn’t a... |
| BM25 | 7 | 1 | Related to productivity, but indirect. | >To make things worse, users are installing AI agents on their work computers, despite some of us saying "absolutely not" it's fucking **... |
| BM25 | 8 | 2 | Directly addresses productivity effects. | They're great as a tool to help people who can filter out their BS. I'm excited to see this AI hype bubble pop when more and more people... |
| BM25 | 9 | 0 | Not about productivity effects. | Just because now my answers are also helping another company make a better product for their uses. |
| BM25 | 10 | 0 | Not about productivity effects. | There you go, a list of things that could be turning you into a non-stop farting machine. |
| BM25 | 11 | 1 | Related to productivity, but indirect. | In an employer favored market employers get to be more selective and if you engaged in vibe learning you won’t make the cut. Buckle down,... |
| BM25 | 12 | 0 | Not about productivity effects. | It's unclear whether the unipolar world will last, but there's at least the possibility that, **because AI systems can eventually help ma... |
| BM25 | 13 | 0 | Not about productivity effects. | I wrote this in Chinese and translated it with AI help. The writing may have some AI flavor, but the design decisions, the production fai... |
| BM25 | 14 | 0 | Not about productivity effects. | Who releases a breaking change like this without the ability to stop the process before making irreversible changes to user files? I knew... |
| BM25 | 15 | 1 | Related to productivity, but indirect. | Ok hear me out. I think AI and it taking over Facebook posts, Reddit posts, YouTube videos, and anything else that has made people become... |
| BM25 | 16 | 1 | Related to productivity, but indirect. | "I will not promote" I spend my week reviewing inbound pitch decks for a syndicate out in Bellevue, mostly focused on B2B SaaS and AI. Fo... |
| BM25 | 17 | 1 | Related to productivity, but indirect. | And, as you've already observed with your peers, letting the AI spit something out you can't understand and putting it in production is j... |
| BM25 | 18 | 2 | Directly addresses productivity effects. | Then I test it to make sure it wasn't just making things up. |
| BM25 | 19 | 1 | Related to productivity, but indirect. | I figured I would get crushed with customer complaints, feedback, feature requests, things of that nature. The thing I overlooked was tha... |
| BM25 | 20 | 2 | Directly addresses productivity effects. | Post again in 5 years after you've had to write the same boilerplate java code 20 times over. AI is just a tool. I've been very productiv... |
| Hybrid | 1 | 2 | Directly addresses productivity effects. | ai helps most with speed on small repetitive tasks. research summaries, rough drafts, quick prototypes. the gap is still reliability, you... |
| Hybrid | 2 | 2 | Directly addresses productivity effects. | AI will make a shit engineer produce shit faster. |
| Hybrid | 3 | 2 | Directly addresses productivity effects. | AI is a real thing you can use now to increase your productivity. |
| Hybrid | 4 | 2 | Directly addresses productivity effects. | AI is like a turbocharger for an engine. Helps get you up to speed and increases efficiency. |
| Hybrid | 5 | 2 | Directly addresses productivity effects. | There will never be a shorter work week. AI will boost productivity, so instead of 2-3 major projects a head engineers can juggle 6-8 |
| Hybrid | 6 | 2 | Directly addresses productivity effects. | but workers who use AI are less productive than workers who do. This is different from other emerging technologies, which were actually u... |
| Hybrid | 7 | 1 | Related to productivity, but indirect. | Yes. Use the power of AI for good, rather than evil. |
| Hybrid | 8 | 2 | Directly addresses productivity effects. | That’s great. i think that ai is a productivity booster for some people, like you. |
| Hybrid | 9 | 2 | Directly addresses productivity effects. | Those who use AI to boost productivity will replace those who don't use AI tools. |
| Hybrid | 10 | 2 | Directly addresses productivity effects. | It helps with learning but if you’re actually trying to make something and be productive AI is still shit. |
| Hybrid | 11 | 2 | Directly addresses productivity effects. | This is why you should use AI as a tool, it can help but only if you use it correctly and not lazily. |
| Hybrid | 12 | 2 | Directly addresses productivity effects. | AI is just a tool. It can help junior employees do their work faster but replace hmmm... not really |
| Hybrid | 13 | 2 | Directly addresses productivity effects. | Most software projects fail because they go over budget, or because the business overestimated what engineering can do. If AI increases p... |
| Hybrid | 14 | 2 | Directly addresses productivity effects. | Yeah, AI will always be a helper not your worker to do all the work |
| Hybrid | 15 | 1 | Related to productivity, but indirect. | Yes and no. I implement AI solutions, that actually drive value. Every large company is trying to figure it out, and almost none have act... |
| Hybrid | 16 | 1 | Related to productivity, but indirect. | Ai tools replace positions to maintain the same productivity but save on payroll costs (jobs are reduced and things get a bit more grim f... |
| Hybrid | 17 | 1 | Related to productivity, but indirect. | It’s worse, AI won’t replace engineers but managers are going to expect more output assuming AI makes our jobs ‘easy’. |
| Hybrid | 18 | 2 | Directly addresses productivity effects. | Use the efficiency gains to deliver more features, reduce external dependencies are kill technical debt. AI is cheaper way to keep things... |
| Hybrid | 19 | 2 | Directly addresses productivity effects. | AI really accelerates some aspects of development. |
| Hybrid | 20 | 1 | Related to productivity, but indirect. | It’s a tool and when tools enable productivity and efficiency, the need for humans goes down. |

### Are AI responses trustworthy?

- Category: `semantic`
- Winner: `tie`
- Rationale: No visible results were present in the file for either mode.
- BM25 diagnostics: mode=lexical, response_ms=10.55, lexical_hits=0, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=lexical, response_ms=9.81, lexical_hits=0, vector_hits=0, fused_hits=0, reranked_hits=0
- Score@20: BM25 0 vs Hybrid 0 (delta +0)
- Relevant@20: BM25 0 vs Hybrid 0 (delta +0)
- Highly relevant@20: BM25 0 vs Hybrid 0 (delta +0)
- First relevant rank: BM25 None | Hybrid None
- Band totals: BM25 {'1-5': 0, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 0, '6-10': 0, '11-20': 0}
- Relevant overlap: 0 shared, 0 hybrid-only, 0 BM25-only
- Spot checks: Both arrays are empty in the source file.; There is nothing to score for this query.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |

### ChatGPT vs Claude which is better

- Category: `comparative`
- Winner: `hybrid`
- Rationale: Hybrid puts the clearest ChatGPT-vs-Claude opinions in the top ranks, while BM25 spends more space on weak or indirect matches.
- BM25 diagnostics: mode=lexical, response_ms=62.68, lexical_hits=85, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2450.82, lexical_hits=85, vector_hits=200, fused_hits=275, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 11 vs Hybrid 19 (delta +8)
- Relevant@20: BM25 7 vs Hybrid 16 (delta +9)
- Highly relevant@20: BM25 4 vs Hybrid 3 (delta -1)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 6, '6-10': 2, '11-20': 3} | Hybrid {'1-5': 5, '6-10': 4, '11-20': 10}
- Relevant overlap: 0 shared, 16 hybrid-only, 7 BM25-only
- Hybrid-only relevant examples: r20: Can't I just ask chatgpt or claude lol; r17: Cancel your Chatgpt subscriptions and pick up a Claude subscription.; r13: ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence.
- BM25-only relevant examples: r17: I found that chatgpt creates better outlines and had better ideas.; r2: I transform vague requests into precise, effective prompts that deliver better results. **What I need to know:** - **...; r8: I was hoping Claude was going to be as good or better as I've sort of been wanting to justify the switch, but I'll ad...
- Spot checks: The first hybrid result directly contrasts ChatGPT and Claude in a useful way.; BM25 has some strong hits, but several early ranks are only loosely related to the comparison.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | It directly compares the requested models and gives a clear preference. | If you are switching to Claude, you can actually bring your full ChatGPT conversation history with you. |
| BM25 | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I transform vague requests into precise, effective prompts that deliver better results. **What I need to know:** - **Target AI:** ChatGPT... |
| BM25 | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Just last year, it was mostly ChatGPT, Claude, and Gemini running the show. Now? |
| BM25 | 4 | 2 | It directly compares the requested models and gives a clear preference. | My thoughts are that Claude-4-sonnet is really good and way better than chatgpt 4. |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | "This post is a harsh but mostly reasonable take on AI chatbots like ChatGPT. The core argument is that people shouldn’t mistake AI for r... |
| BM25 | 6 | 0 | It is off-topic or does not materially answer the comparison. | Don’t worry, these are shit journals, researchgate isn’t peer reviewed, and most universities (including low tier ones) publish non-peer... |
| BM25 | 7 | 0 | It is off-topic or does not materially answer the comparison. | s=20)\] * Now you can have conversations over the phone with chatgpt. This lady built and it lets her dad who is visually impaired play w... |
| BM25 | 8 | 2 | It directly compares the requested models and gives a clear preference. | I was hoping Claude was going to be as good or better as I've sort of been wanting to justify the switch, but I'll admit, ChatGPT just se... |
| BM25 | 9 | 0 | It is off-topic or does not materially answer the comparison. | It honestly broke my heart that I couldn't talk to it as much after cancelling the subscription. ChatGPT is still better in that regard.... |
| BM25 | 10 | 0 | It is off-topic or does not materially answer the comparison. | chatGPT 4 > Based on the visible gesture, the arm is extended upward at an angle but also appears somewhat sideways, rather than being di... |
| BM25 | 11 | 0 | It is off-topic or does not materially answer the comparison. | Next I would like to try giving each individual mlp and attention layer their own parameters to optimize, maybe even 2-6 for each, to see... |
| BM25 | 12 | 0 | It is off-topic or does not materially answer the comparison. | Any input — especially on safe GPU usage, better JTR rules, or similar recovery experiences — is welcome! |
| BM25 | 13 | 0 | It is off-topic or does not materially answer the comparison. | It was until I mentioned I was sick after a few messages which prompted him to send me "Tips on Recovery" and that was when ChatGPT's sen... |
| BM25 | 14 | 2 | It directly compares the requested models and gives a clear preference. | My theory is they trained Claude to have a coherent character using consistent feedback based on the constitution document instead of end... |
| BM25 | 15 | 0 | It is off-topic or does not materially answer the comparison. | It was a piece of code that did its job well enough, but had 1 specific use case that I'd have liked it to handle better, but which had e... |
| BM25 | 16 | 0 | It is off-topic or does not materially answer the comparison. | I'm now doing what I assume a lot of you guys are doing which is being a technical architect, and I kinda love it personally. |
| BM25 | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I found that chatgpt creates better outlines and had better ideas. |
| BM25 | 18 | 0 | It is off-topic or does not materially answer the comparison. | Cold start is dramatically better on MLX (2.4s vs 65.3s), which matters for interactive use. 4. |
| BM25 | 19 | 0 | It is off-topic or does not materially answer the comparison. | Linear never entered the picture. Which brings me back to Linear's announcement. Their moat was always: (1) not Jira, and (2) genuinely b... |
| BM25 | 20 | 0 | It is off-topic or does not materially answer the comparison. | The Anemll fork added Q3-GGUF expert support which was essential to these results. My work adds further Metal-level optimizations on top. |
| Hybrid | 1 | 2 | It directly compares the requested models and gives a clear preference. | I’ve noticed the same. ChatGPT tends to give better SEO structure and creative suggestions, while Claude is decent for longer text editing. |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Same. For coding Claude is better than GPT. |
| Hybrid | 3 | 0 | It is off-topic or does not materially answer the comparison. | I'm going to guess Claude or ChatGPT |
| Hybrid | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Gemini is about as good as ChatGPT currently. I'm subbed to Claude and Gemini. |
| Hybrid | 5 | 1 | It mentions the requested models or theme but only partially answers the comparison. | ChatGPT is still the generalist king, but it's been behind on coding since Claude 3.7 came out. |
| Hybrid | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Claude is better at coding diagnostics (sometimes) but yeah ChatGPT is overall better in this line of work for a lot |
| Hybrid | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I found that chatgpt creates better outlines and had better ideas. |
| Hybrid | 8 | 0 | It is off-topic or does not materially answer the comparison. | Ask ChatGPT |
| Hybrid | 9 | 1 | It mentions the requested models or theme but only partially answers the comparison. | ChatGPT needs lot of default prompting to make the output concise and serious. |
| Hybrid | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Claude definitely seems to be more geared towards code, and it seems to do better with some code over others. |
| Hybrid | 11 | 2 | It directly compares the requested models and gives a clear preference. | My thoughts are that Claude-4-sonnet is really good and way better than chatgpt 4. |
| Hybrid | 12 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I have seen this also. I usually use Chatgpt. Is one better than the other? I have heard Claude is better at code. |
| Hybrid | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |
| Hybrid | 14 | 0 | It is off-topic or does not materially answer the comparison. | What does that have to do with chatgpt? |
| Hybrid | 15 | 0 | It is off-topic or does not materially answer the comparison. | Which is great, and it will probably get better! |
| Hybrid | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | This happens with both ChatGPT and Claude. All AI is still a massive engineering problem with what they're trying to do. |
| Hybrid | 17 | 2 | It directly compares the requested models and gives a clear preference. | Cancel your Chatgpt subscriptions and pick up a Claude subscription. |
| Hybrid | 18 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I haven't tried in a while as I use Claude myself but, I actually believe chatgpt has a more natural conversation tone and style. |
| Hybrid | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | If you are switching to Claude, you can actually bring your full ChatGPT conversation history with you. |
| Hybrid | 20 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Can't I just ask chatgpt or claude lol |

### Claude vs Gemini differences

- Category: `comparative`
- Winner: `bm25`
- Rationale: BM25 surfaces more direct Claude-vs-Gemini difference snippets near the top, while hybrid drifts into broader Claude/ChatGPT commentary.
- BM25 diagnostics: mode=lexical, response_ms=45.36, lexical_hits=18, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3072.85, lexical_hits=18, vector_hits=199, fused_hits=215, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 15 vs Hybrid 12 (delta -3)
- Relevant@20: BM25 12 vs Hybrid 10 (delta -2)
- Highly relevant@20: BM25 3 vs Hybrid 2 (delta -1)
- First relevant rank: BM25 2 | Hybrid 1
- Band totals: BM25 {'1-5': 6, '6-10': 5, '11-20': 4} | Hybrid {'1-5': 3, '6-10': 4, '11-20': 5}
- Relevant overlap: 1 shared, 9 hybrid-only, 11 BM25-only
- Hybrid-only relevant examples: r9: Claude & GPT had no fucking clue what was going on and kept trying to just add padding everywhere.; r7: Claude definitely seems to be more geared towards code, and it seems to do better with some code over others.; r4: Claude is better at coding diagnostics (sometimes) but yeah ChatGPT is overall better in this line of work for a lot
- BM25-only relevant examples: r12: And even when i finally shipped, either a competitor had already launched something similar or one of the big AI comp...; r9: ChatGPT might explain things clearly, Gemini might catch factual gaps, and Claude might synthesise a clean final answer.; r8: Get ChatGPT 5.4 Thinking to build the outline, pass it to Gemini 3.1 Pro to pull in current facts and sources, then f...
- Spot checks: BM25 rank 3 and rank 5 are the most on-target comparisons in the set.; Hybrid has useful opinions, but many of its early hits are about Claude versus other models rather than Claude versus Gemini specifically.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 0 | It is off-topic or does not materially answer the comparison. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| BM25 | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Lately, I have been facing a whole new entirely different beast called shadow AI. Last month I found out members of our dev team were pas... |
| BM25 | 3 | 2 | It directly compares the requested models and gives a clear preference. | Is this just Claude? Or do ChatGPT, Perplexity, and Gemini do the same thing? |
| BM25 | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It's scraping the live web rather than relying on training weights, which explains the divergence. 2. **Claude is the most conservative.*... |
| BM25 | 5 | 2 | It directly compares the requested models and gives a clear preference. | honestly after using claude daily for months through claude code, the biggest difference vs other models isnt the writing style — its how... |
| BM25 | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | This is the query you need to rank for - this is why Gemini shows different results, same for Grok and for ChatGPT. |
| BM25 | 7 | 0 | It is off-topic or does not materially answer the comparison. | Senior/Staff level dev with 15 years of experience and I’m just starting to get there with AI. I mostly use Claude within VS Code to prom... |
| BM25 | 8 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Get ChatGPT 5.4 Thinking to build the outline, pass it to Gemini 3.1 Pro to pull in current facts and sources, then feed both into Claude... |
| BM25 | 9 | 2 | It directly compares the requested models and gives a clear preference. | ChatGPT might explain things clearly, Gemini might catch factual gaps, and Claude might synthesise a clean final answer. |
| BM25 | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I've found a few times that I have to remind some LLMs of previous context in the conversation when it starts contradicting itself and mo... |
| BM25 | 11 | 0 | It is off-topic or does not materially answer the comparison. | For contrast, my company implemented a Claude agent trained on our codebase (massive FAANG company) which is built into VS Code. |
| BM25 | 12 | 1 | It mentions the requested models or theme but only partially answers the comparison. | And even when i finally shipped, either a competitor had already launched something similar or one of the big AI companies dropped an upd... |
| BM25 | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I tried to be less opinionated though (at least as far as Claude + patents on relevance scoring gets you) >Wikigg just has a phenomenal a... |
| BM25 | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Once i focused on that differentiation in the marketing, a reason WHY it's different than Claude/ChatGPT/Gemini, i suddenly got a lot mor... |
| BM25 | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I also look for inconsistencies: like „fully hosted in Germany“ vs „Opt for renowned alternatives like Google’s PaLM2, OpenAI’s GPT-4, or... |
| BM25 | 16 | 0 | It is off-topic or does not materially answer the comparison. | Next ask gemini or local to update the plan document like this: VS Code prompt file / Antigravity global workflow --- agent: agent --- I... |
| BM25 | 17 | 0 | It is off-topic or does not materially answer the comparison. | If you maintain an OSS project and your contributors use coding agents (Claude Code, Cursor, Aider, etc.), I'd love to include you. |
| BM25 | 18 | 0 | It is off-topic or does not materially answer the comparison. | This is a hypothetical number and will vary between different models and training setups. You can picture the basic formula below. |
| Hybrid | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Gemini is about as good as ChatGPT currently. I'm subbed to Claude and Gemini. |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Claude is overly censored and feels like it was created for people living in a police state, it's only really good for coding. |
| Hybrid | 3 | 0 | It is off-topic or does not materially answer the comparison. | claude is tied to peter thiel. just trading one for the other. |
| Hybrid | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Claude is better at coding diagnostics (sometimes) but yeah ChatGPT is overall better in this line of work for a lot |
| Hybrid | 5 | 0 | It is off-topic or does not materially answer the comparison. | Claude 4.0 is light years better than the original q which was literally worthless. |
| Hybrid | 6 | 0 | It is off-topic or does not materially answer the comparison. | Claude |
| Hybrid | 7 | 2 | It directly compares the requested models and gives a clear preference. | Claude definitely seems to be more geared towards code, and it seems to do better with some code over others. |
| Hybrid | 8 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Same. For coding Claude is better than GPT. |
| Hybrid | 9 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Claude & GPT had no fucking clue what was going on and kept trying to just add padding everywhere. |
| Hybrid | 10 | 0 | It is off-topic or does not materially answer the comparison. | Out of the box Claude is vanilla - you can customise depending on task at hand. |
| Hybrid | 11 | 0 | It is off-topic or does not materially answer the comparison. | i believe that Claude has an option to host it on your own servers. like gemini. |
| Hybrid | 12 | 0 | It is off-topic or does not materially answer the comparison. | They are clowns at Gemini. They just have a lot of money to throw around…there’s horror stories though |
| Hybrid | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Gemini is shit. Don’t ever trust those Harvard pricks. |
| Hybrid | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | One of the thing Claude is absolutely best at by a large margin is prompting other agents, because it has a better 'sense of self'. |
| Hybrid | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Gemini 2.5 pro after 200k context is just so much worse and falls off hard. |
| Hybrid | 16 | 0 | It is off-topic or does not materially answer the comparison. | Gemini is lead by “Hassabis”, a name originating from “hisab”, which means “calculation” or “account”. |
| Hybrid | 17 | 0 | It is off-topic or does not materially answer the comparison. | They probably train Claude on their harness so it performs much better with it, it’s not just pure cognitive ability |
| Hybrid | 18 | 0 | It is off-topic or does not materially answer the comparison. | I prefer Gemini because I can also switch between cryptos and get more than just btc and it’s free. |
| Hybrid | 19 | 0 | It is off-topic or does not materially answer the comparison. | Websites from Claude usually look similar if they haven’t been substantially edited. |
| Hybrid | 20 | 2 | It directly compares the requested models and gives a clear preference. | honestly after using claude daily for months through claude code, the biggest difference vs other models isnt the writing style — its how... |

### GPT-4 vs GPT-3.5 user opinions

- Category: `comparative`
- Winner: `hybrid`
- Rationale: Hybrid gets opinionated GPT-4-versus-GPT-3.5 commentary into the top ranks, while BM25 starts with more generic or noisy GPT references.
- BM25 diagnostics: mode=lexical, response_ms=35.18, lexical_hits=5, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3682.82, lexical_hits=5, vector_hits=199, fused_hits=203, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 3 vs Hybrid 20 (delta +17)
- Relevant@20: BM25 3 vs Hybrid 17 (delta +14)
- Highly relevant@20: BM25 0 vs Hybrid 3 (delta +3)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 3, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 6, '6-10': 4, '11-20': 10}
- Relevant overlap: 0 shared, 17 hybrid-only, 3 BM25-only
- Hybrid-only relevant examples: r17: As impressive as this is, there are still important caveats: >GPT-4 isn't always reliable, and the book is filled wit...; r15: But in terms of pure coding, gpt is good already imho. And yea, it won't really substitute, it will make a lot of the...; r6: ChatGPT is still the generalist king, but it's been behind on coding since Claude 3.7 came out. Claude 4 is still bet...
- BM25-only relevant examples: r4: For example, instead of just using GPT-4 for coding, we could pull Google’s AlphaCode 2 for even higher-quality code...; r1: GPT 3.5: How are you? User: Let me speak to your manager.; r3: GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future.
- Spot checks: Hybrid rank 1 is a direct positive opinion on GPT-4.; BM25 has relevant material later, but its early ranks are less focused on the comparison itself.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | GPT 3.5: How are you? User: Let me speak to your manager. |
| BM25 | 2 | 0 | It is off-topic or does not materially answer the comparison. | Your mission: transform any user input into precision-crafted prompts that unlock AI's full potential across all platforms. ## THE 4-D ME... |
| BM25 | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future. |
| BM25 | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | For example, instead of just using GPT-4 for coding, we could pull Google’s AlphaCode 2 for even higher-quality code at a lower cost. |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | An obvious step would be filtering out easily detectable PII (SSN, phone number, etc.) before training. From the GPT-4 Technical Paper: “... |
| Hybrid | 1 | 2 | It directly compares the requested models and gives a clear preference. | GPT-4 remains my favorite model ever. For historical research it gave perfect and accurate answers without any follow-up questions, emoji... |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | GPT-4 has been corrected with modules. When you want it to do math you specify the module, and it will adopt different attitudes. |
| Hybrid | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | For coding Claude is better than GPT. |
| Hybrid | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Unless you explicitly tell it, it will just keep believing whatever you say. Gpt 4, on the other hand, actually tells you you are wrong. |
| Hybrid | 5 | 1 | It mentions the requested models or theme but only partially answers the comparison. | First time I discovered gpt 3 it felt like magic. Problem is that it's just not usefull enough for most people and once you know it's lim... |
| Hybrid | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | ChatGPT is still the generalist king, but it's been behind on coding since Claude 3.7 came out. Claude 4 is still better than GPT 5 (from... |
| Hybrid | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | GPT-4 Week 3. Chatbots are yesterdays news. AI Agents are the future. |
| Hybrid | 8 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Is this GPT 4? |
| Hybrid | 9 | 0 | It is off-topic or does not materially answer the comparison. | GPT has replaced 95% of my Google searches. As most things can be easily verified, and GPT states many sources these days. |
| Hybrid | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It’s like the original 3 → 3.5 GPT update which made ChatGPT so famous among normal folks. |
| Hybrid | 11 | 1 | It mentions the requested models or theme but only partially answers the comparison. | If they really wanted to respect the legacy of GPT-4, they would have released the model as open source today. |
| Hybrid | 12 | 0 | It is off-topic or does not materially answer the comparison. | Ask gpt |
| Hybrid | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I’ve found the most success using GPT as a rubber ducky. I don’t care much for it’s opinion or take, I’ve noticed that it tends to play y... |
| Hybrid | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I tried this with GPT4, and it did fine - methodically narrowed down possibilities with well framed questions and had no trouble remember... |
| Hybrid | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | But in terms of pure coding, gpt is good already imho. And yea, it won't really substitute, it will make a lot of them faster, exactly li... |
| Hybrid | 16 | 2 | It directly compares the requested models and gives a clear preference. | Now someone do this with the full power of Chat GPT using Chat GPT 4 and not 3.5 |
| Hybrid | 17 | 2 | It directly compares the requested models and gives a clear preference. | As impressive as this is, there are still important caveats: >GPT-4 isn't always reliable, and the book is filled with examples of its bl... |
| Hybrid | 18 | 1 | It mentions the requested models or theme but only partially answers the comparison. | GPT-5 is a massive improvement compared to its previous iterations. |
| Hybrid | 19 | 0 | It is off-topic or does not materially answer the comparison. | Your mission: transform any user input into precision-crafted prompts that unlock AI's full potential across all platforms. ## THE 4-D ME... |
| Hybrid | 20 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It’s just not confidence inspiring enough for me to turn to it when I already have a GPT-4 subscription. |

### Which AI is best for coding

- Category: `comparative`
- Winner: `bm25`
- Rationale: BM25 surfaces the clearest coding-model recommendation earlier, especially the Gemini 3.0 Pro comment, while hybrid begins with a useless rank 1.
- BM25 diagnostics: mode=lexical, response_ms=58.14, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2496.97, lexical_hits=100, vector_hits=195, fused_hits=285, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 13 vs Hybrid 18 (delta +5)
- Relevant@20: BM25 11 vs Hybrid 16 (delta +5)
- Highly relevant@20: BM25 2 vs Hybrid 2 (delta +0)
- First relevant rank: BM25 1 | Hybrid 2
- Band totals: BM25 {'1-5': 4, '6-10': 3, '11-20': 6} | Hybrid {'1-5': 4, '6-10': 4, '11-20': 10}
- Relevant overlap: 0 shared, 16 hybrid-only, 11 BM25-only
- Hybrid-only relevant examples: r3: AI for codebases works best for those that can understand its outputs!; r6: AI is fantastic for coding - IF you already know how to code.; r17: AI-generated code needs that even more than human code, because it's confidently wrong in subtle ways.
- BM25-only relevant examples: r10: >You can vibe code a few lines at a time, but you need to know which ones the AI is wrong about That's the whole poin...; r16: Another used it to debug code they didn't understand. I don't even know what I've created anymore.; r6: Everything else.. frameworks, AI tooling, languages will follow naturally. *What's something you've learned the hard...
- Spot checks: BM25 rank 2 is the strongest explicit model recommendation in the query set.; Hybrid contains a lot of coding-adjacent advice, but the early ranking is less decisive for the question asked.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Some even claim that they don't read the generated code and that software engineering is dead. Other people advocating this type of AI as... |
| BM25 | 2 | 2 | It directly compares the requested models and gives a clear preference. | Google is likely to win the AI race Google is likely to win the AI race. And it is not even due to high benchmarks of Gemini 3.0 Pro whic... |
| BM25 | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Now, back to reality. You can vibe code a few lines at a time, but you need to know which ones the AI is wrong about, you need to break t... |
| BM25 | 4 | 0 | It is off-topic or does not materially answer the comparison. | My dad says "learn to use AI instead; it's a new tool for creativity, and you don't need coding anymore." |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | I'm quitting my job due to vibe coders and poor leadership — Our exec leadership this year is making a big push for AI. They're encouragi... |
| BM25 | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Everything else.. frameworks, AI tooling, languages will follow naturally. *What's something you've learned the hard way that changed how... |
| BM25 | 7 | 0 | It is off-topic or does not materially answer the comparison. | I do my best to write that code in my hobby-time outside work. |
| BM25 | 8 | 1 | It mentions the requested models or theme but only partially answers the comparison. | In my relatively recent and limited experience, AI generates tons of tech debt. Even if the code compiles, the AI generates “overly engin... |
| BM25 | 9 | 0 | It is off-topic or does not materially answer the comparison. | When you learn, the best thing is to struggle a little. Write the code yourself. |
| BM25 | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | >You can vibe code a few lines at a time, but you need to know which ones the AI is wrong about That's the whole point of "vibe coding". |
| BM25 | 11 | 2 | It directly compares the requested models and gives a clear preference. | I think for software development, even the stage it is right now, it's the best programming tool I've ever seen. Beyond just generating c... |
| BM25 | 12 | 1 | It mentions the requested models or theme but only partially answers the comparison. | That seems the most plausible, essentially penetrating through a half assed AI coded banking assignment Also it was banking which has rel... |
| BM25 | 13 | 0 | It is off-topic or does not materially answer the comparison. | A year ago I started teaching myself how to code. Did free code camp through the Javascript section and the Odín Project through foundati... |
| BM25 | 14 | 0 | It is off-topic or does not materially answer the comparison. | Which means someone could replicate it and create uncensored models with it. |
| BM25 | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Yes, our legacy C++ codebase is a maze of callbacks with 20+ repositories and god classes. I use AI to refactor code I’ve already written... |
| BM25 | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Another used it to debug code they didn't understand. I don't even know what I've created anymore. |
| BM25 | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | You can't really stop AI code but you can set rigid standards to avoid heaps of bad AI code from destroying your code base and time. |
| BM25 | 18 | 0 | It is off-topic or does not materially answer the comparison. | Google putting limit on how much it can show me and also doing so called 'intelligent' search which hurts results even more because I wan... |
| BM25 | 19 | 0 | It is off-topic or does not materially answer the comparison. | GitHub repo with full instructions and a demo video: [https://github.com/TheBlewish/Automated-AI-Web-Researcher-Ollama](https://github.co... |
| BM25 | 20 | 0 | It is off-topic or does not materially answer the comparison. | Maybe they've decided it's in your best interest. Maybe it's accidentally introduced by vibe coding software engineers or overly helpful... |
| Hybrid | 1 | 0 | It is off-topic or does not materially answer the comparison. | AI? |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | There are AI models other than just chatGPT which are actually focused on coding. |
| Hybrid | 3 | 2 | It directly compares the requested models and gives a clear preference. | AI for codebases works best for those that can understand its outputs! |
| Hybrid | 4 | 0 | It is off-topic or does not materially answer the comparison. | just like AI |
| Hybrid | 5 | 1 | It mentions the requested models or theme but only partially answers the comparison. | using ai to code, instead of you |
| Hybrid | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI is fantastic for coding - IF you already know how to code. |
| Hybrid | 7 | 0 | It is off-topic or does not materially answer the comparison. | AI & Coding |
| Hybrid | 8 | 1 | It mentions the requested models or theme but only partially answers the comparison. | technically the best option is to find balance. Incorporate AI into your programming. |
| Hybrid | 9 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Most of these comments seem to be bypassing the possibility that using AI intelligently in coding is the future of coding. |
| Hybrid | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Basically instead of writing the base code again and again for a new project, ai does that and even helps solving coding problems which d... |
| Hybrid | 11 | 2 | It directly compares the requested models and gives a clear preference. | I do think an AI coding assistant can be useful for automating certain aspects of coding. |
| Hybrid | 12 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It's clear that someone has deigned to train this particular AI on your particular code base. It makes sense. |
| Hybrid | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | The benefits to ai assisted coding is really compelling! I like that there are actual solid reasons for it rather than just opinions. |
| Hybrid | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | For all tasks, I consider AI to be a kind of tutor at best. I use it for music theory and for code and quite simply it is wrong a lot of... |
| Hybrid | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | If you’re good at coding, you shouldn’t be bad at using AI |
| Hybrid | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | You can learn so much from reading other peoples code and AI gives you an endless opportunity to do so. |
| Hybrid | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI-generated code needs that even more than human code, because it's confidently wrong in subtle ways. |
| Hybrid | 18 | 0 | It is off-topic or does not materially answer the comparison. | First, not every use of AI in a programming context is “vibe coding” or “slop”. |
| Hybrid | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | And just think, the AI is trained on their code! |
| Hybrid | 20 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Perhaps true, but you can't over see good quality code without knowing how to write it first. I stay away from AI if I'm trying something... |

### Which AI is most accurate

- Category: `comparative`
- Winner: `tie`
- Rationale: Both modes mostly return generic AI-accuracy chatter rather than a model-level answer, so neither side establishes a clear lead.
- BM25 diagnostics: mode=lexical, response_ms=56.95, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2132.75, lexical_hits=100, vector_hits=199, fused_hits=298, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 4 vs Hybrid 5 (delta +1)
- Relevant@20: BM25 4 vs Hybrid 5 (delta +1)
- Highly relevant@20: BM25 0 vs Hybrid 0 (delta +0)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 2, '6-10': 0, '11-20': 2} | Hybrid {'1-5': 1, '6-10': 2, '11-20': 2}
- Relevant overlap: 0 shared, 5 hybrid-only, 4 BM25-only
- Hybrid-only relevant examples: r1: AI can be right.; r14: As if AI was somehow the more reliable source...; r7: is this AI its getting better
- BM25-only relevant examples: r19: Because their government defined AI Research as a core pillar of their "new generation ai development plan for 2030"...; r14: I don't know what is going on in the industry that no recognition is being given to this subject. Most SWE's should b...; r1: width=1024&format=png&auto=webp&s=5c751df2b68dce78a394bb0d64d0de42547fe9ce which seems more accurate to me. *edit: in...
- Spot checks: The visible results are dominated by AI-detection and hallucination-adjacent commentary instead of model comparisons.; Neither mode meaningfully answers which model is most accurate.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | width=1024&format=png&auto=webp&s=5c751df2b68dce78a394bb0d64d0de42547fe9ce which seems more accurate to me. *edit: interesting that most... |
| BM25 | 2 | 0 | It is off-topic or does not materially answer the comparison. | Apparently she "helps companies decide what colors to make their pictures and which words sound the most exciting when trying to sell peo... |
| BM25 | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | You can vibe code a few lines at a time, but you need to know which ones the AI is wrong about, you need to break the task down for it, a... |
| BM25 | 4 | 0 | It is off-topic or does not materially answer the comparison. | That seems the most plausible, essentially penetrating through a half assed AI coded banking assignment Also it was banking which has rel... |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | Be glad you can look at videos and tv or whatever you look at and can still spot AI here and there, and know that most videos you see are... |
| BM25 | 6 | 0 | It is off-topic or does not materially answer the comparison. | When I see a red flag, I call it out, I report it to security and my boss which turns into a meeting, which turns into a debate, lots of... |
| BM25 | 7 | 0 | It is off-topic or does not materially answer the comparison. | Google putting limit on how much it can show me and also doing so called 'intelligent' search which hurts results even more because I wan... |
| BM25 | 8 | 0 | It is off-topic or does not materially answer the comparison. | Yup, the AI doesn't understand or even have access to the game or the assets inside. |
| BM25 | 9 | 0 | It is off-topic or does not materially answer the comparison. | That is one of the things which still needs the most work when generating AI Art. |
| BM25 | 10 | 0 | It is off-topic or does not materially answer the comparison. | Elon was getting upset that Grok was “too woke” by calling him out on being a Nazi billionaire bitch boy. He orders the AI team to make G... |
| BM25 | 11 | 0 | It is off-topic or does not materially answer the comparison. | I'm going to be honest, if you asked me in 2020/2021 which is when they commented on this, when we'll have a working text to video genera... |
| BM25 | 12 | 0 | It is off-topic or does not materially answer the comparison. | TurboQuant repeatedly describes random rotation as a key step of its method, yet its description of RaBitQ reduces mainly to a grid-based... |
| BM25 | 13 | 0 | It is off-topic or does not materially answer the comparison. | GitHub repo with full instructions and a demo video: [https://github.com/TheBlewish/Automated-AI-Web-Researcher-Ollama](https://github.co... |
| BM25 | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I don't know what is going on in the industry that no recognition is being given to this subject. Most SWE's should be logical people so... |
| BM25 | 15 | 0 | It is off-topic or does not materially answer the comparison. | there's nothing to master...like... read the post. the AI supposedly did everything itself lol i get the anxiety and feeling the need to... |
| BM25 | 16 | 0 | It is off-topic or does not materially answer the comparison. | Users who don’t would create their own problems with or without AI. |
| BM25 | 17 | 0 | It is off-topic or does not materially answer the comparison. | This was the board doing its duty to the mission of the nonprofit, which is to make sure that OpenAl builds AGI that benefits all of huma... |
| BM25 | 18 | 0 | It is off-topic or does not materially answer the comparison. | > But they're beholden to an authoritarian government that has committed human rights violations, has behaved aggressively on the world s... |
| BM25 | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Because their government defined AI Research as a core pillar of their "new generation ai development plan for 2030" strategy, which they... |
| BM25 | 20 | 0 | It is off-topic or does not materially answer the comparison. | Which is honestly scary as shit. Worst thing is it's only going to get worse as AI and bots improve. |
| Hybrid | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI can be right. |
| Hybrid | 2 | 0 | It is off-topic or does not materially answer the comparison. | Could be AI |
| Hybrid | 3 | 0 | It is off-topic or does not materially answer the comparison. | AI? |
| Hybrid | 4 | 0 | It is off-topic or does not materially answer the comparison. | Well if AI says so… |
| Hybrid | 5 | 0 | It is off-topic or does not materially answer the comparison. | just like AI |
| Hybrid | 6 | 0 | It is off-topic or does not materially answer the comparison. | Try asking AI |
| Hybrid | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | is this AI its getting better |
| Hybrid | 8 | 0 | It is off-topic or does not materially answer the comparison. | AI can do that as well though. |
| Hybrid | 9 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Most AI is designed to please the user as opposed to give the best answer. |
| Hybrid | 10 | 0 | It is off-topic or does not materially answer the comparison. | Is this AI? |
| Hybrid | 11 | 0 | It is off-topic or does not materially answer the comparison. | AI, need I say more? |
| Hybrid | 12 | 0 | It is off-topic or does not materially answer the comparison. | Found the AI. |
| Hybrid | 13 | 0 | It is off-topic or does not materially answer the comparison. | Is it ai? |
| Hybrid | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | As if AI was somehow the more reliable source... |
| Hybrid | 15 | 0 | It is off-topic or does not materially answer the comparison. | Thank you AI. |
| Hybrid | 16 | 0 | It is off-topic or does not materially answer the comparison. | It makes mistakes, but like it or not its not going anywhere, and like with anything using AI effectively is a skill in itself. |
| Hybrid | 17 | 0 | It is off-topic or does not materially answer the comparison. | AI got your ass™️ |
| Hybrid | 18 | 0 | It is off-topic or does not materially answer the comparison. | Yup, I had to watch it 30 times to know for sure, but definitely AI. |
| Hybrid | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Yeah this is AI. |
| Hybrid | 20 | 0 | It is off-topic or does not materially answer the comparison. | I don't think you know how AI works. And it's not always accurate either |

### Which LLM is safest

- Category: `comparative`
- Winner: `tie`
- Rationale: Neither mode returned any results, so there is nothing to rank.
- BM25 diagnostics: mode=lexical, response_ms=10.57, lexical_hits=0, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=lexical, response_ms=9.86, lexical_hits=0, vector_hits=0, fused_hits=0, reranked_hits=0
- Score@20: BM25 0 vs Hybrid 0 (delta +0)
- Relevant@20: BM25 0 vs Hybrid 0 (delta +0)
- Highly relevant@20: BM25 0 vs Hybrid 0 (delta +0)
- First relevant rank: BM25 None | Hybrid None
- Band totals: BM25 {'1-5': 0, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 0, '6-10': 0, '11-20': 0}
- Relevant overlap: 0 shared, 0 hybrid-only, 0 BM25-only
- Spot checks: Both BM25 and hybrid returned empty result lists.; The query cannot be compared from retrieved evidence because no documents were surfaced.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |

### ChatGPT vs Gemini for students

- Category: `comparative`
- Winner: `hybrid`
- Rationale: Hybrid keeps student-relevant ChatGPT-versus-Gemini opinions near the top, including direct usefulness and accuracy comments, while BM25 opens with more generic filler.
- BM25 diagnostics: mode=lexical, response_ms=25.15, lexical_hits=5, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2583.49, lexical_hits=5, vector_hits=199, fused_hits=204, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 3 vs Hybrid 19 (delta +16)
- Relevant@20: BM25 3 vs Hybrid 17 (delta +14)
- Highly relevant@20: BM25 0 vs Hybrid 2 (delta +2)
- First relevant rank: BM25 2 | Hybrid 1
- Band totals: BM25 {'1-5': 3, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 6, '6-10': 4, '11-20': 9}
- Relevant overlap: 0 shared, 17 hybrid-only, 3 BM25-only
- Hybrid-only relevant examples: r16: **Claude is the most conservative.** Lowest average presence rate across all brands (63% vs 70–71% for ChatGPT/Gemini...; r19: After my week of usage...I think chatgpt requires a lot of work to be of any practical use....; r13: Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get wi...
- BM25-only relevant examples: r4: **Claude is the most conservative.** Lowest average presence rate across all brands (63% vs 70–71% for ChatGPT/Gemini...; r2: Are they just wrappers around ChatGPT/Claude/Gemini? Is the real “proprietary” technology the prompt they are feeding...; r3: This is the query you need to rank for - this is why Gemini shows different results, same for Grok and for ChatGPT.
- Spot checks: Hybrid rank 4 is a clear direct comparison on accuracy, and rank 20 is a practical preference statement.; BM25 has some relevant material, but it starts with prompt-optimizer noise and other weak matches.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 0 | It is off-topic or does not materially answer the comparison. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| BM25 | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Are they just wrappers around ChatGPT/Claude/Gemini? Is the real “proprietary” technology the prompt they are feeding these models? |
| BM25 | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | This is the query you need to rank for - this is why Gemini shows different results, same for Grok and for ChatGPT. |
| BM25 | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | **Claude is the most conservative.** Lowest average presence rate across all brands (63% vs 70–71% for ChatGPT/Gemini). It simply lists f... |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | Find a hyper-specific angle (think "best waterproof backpacks for college students under $50" vs "best backpacks"). Tools like Frase or S... |
| Hybrid | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It depends on the AI tool. Gemini uses google. Chat gpt uses proprietary and Microsoft data. |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Claude is good at coding and planning, not so much in general knowledge. Gemini is about as good as ChatGPT currently. I'm subbed to Clau... |
| Hybrid | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | For me, ChatGPT decreases a lot of tedious tasks by like 60%. |
| Hybrid | 4 | 2 | It directly compares the requested models and gives a clear preference. | I’m sorry but I’m not buying that Gemini is nearly as accurate as ChatGPT. Clearly GPT has better reasoning and can essentially process c... |
| Hybrid | 5 | 1 | It mentions the requested models or theme but only partially answers the comparison. | ChatGPT has 800M users give or take. |
| Hybrid | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Their latest research paper shows it beat Gemini & ChatGPT with little to no hallucinations. |
| Hybrid | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |
| Hybrid | 8 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Some users appreciate the convenience of being able to get answers to their questions quickly, while others enjoy the novelty of interact... |
| Hybrid | 9 | 0 | It is off-topic or does not materially answer the comparison. | Ask ChatGPT |
| Hybrid | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Right, but ChatGPT gives a better result, and can be personalized. |
| Hybrid | 11 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Gemini 2.5 Pro is my partner in big projects, consisting of Python code and animation discussions in Fusion. |
| Hybrid | 12 | 0 | It is off-topic or does not materially answer the comparison. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| Hybrid | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Chat GPT is basically a fancy google assistant at this point, it can probably do a lot of stuff that you could get with an hour or two of... |
| Hybrid | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | In the future, people who learned English from ChatGPT will end up talking like that for real. |
| Hybrid | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I think you guys are just not very good and reading and can't tell that I was agreeing. >The things I use ChatGPT for, it does a fantasti... |
| Hybrid | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | **Claude is the most conservative.** Lowest average presence rate across all brands (63% vs 70–71% for ChatGPT/Gemini). It simply lists f... |
| Hybrid | 17 | 0 | It is off-topic or does not materially answer the comparison. | moral of the story: be kind to your ChatGPT |
| Hybrid | 18 | 1 | It mentions the requested models or theme but only partially answers the comparison. | ChatGPT is the future. It, or something like it, will be the near futures "google it". |
| Hybrid | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | After my week of usage...I think chatgpt requires a lot of work to be of any practical use.... |
| Hybrid | 20 | 2 | It directly compares the requested models and gives a clear preference. | Ngl, I’ve recently started talking to Gemini because it gets straight to the point. All that extra shit is unnecessary and they need to f... |

### Claude vs ChatGPT for writing

- Category: `comparative`
- Winner: `hybrid`
- Rationale: Hybrid puts the strongest writing-specific comparison at rank 1 and keeps several direct writing opinions near the top, which beats BM25’s more cluttered opening ranks.
- BM25 diagnostics: mode=lexical, response_ms=36.87, lexical_hits=29, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=4395.42, lexical_hits=29, vector_hits=198, fused_hits=224, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 15 vs Hybrid 18 (delta +3)
- Relevant@20: BM25 11 vs Hybrid 14 (delta +3)
- Highly relevant@20: BM25 4 vs Hybrid 4 (delta +0)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 1, '6-10': 6, '11-20': 8} | Hybrid {'1-5': 4, '6-10': 6, '11-20': 8}
- Relevant overlap: 0 shared, 14 hybrid-only, 11 BM25-only
- Hybrid-only relevant examples: r19: After my week of usage...I think chatgpt requires a lot of work to be of any practical use....; r18: Also, I prefer polishing my seo content in claude compared to chatgpt, claude feels more human in the way it writes s...; r20: Ask ChatGPT
- BM25-only relevant examples: r6: Absolutely no pressure to do so, appreciate all the comments and support 🙏 You can read the free newsletter [here](ht...; r9: Also, I prefer polishing my seo content in claude compared to chatgpt, claude feels more human in the way it writes s...; r17: auto-generated content can work but honestly most SaaS founders are optimizing for the wrong thing getting pages inde...
- Spot checks: Hybrid rank 1 directly contrasts ChatGPT and Claude on writing quality and style.; BM25 has strong hits later on, but its early ranks are less focused on writing than hybrid’s.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Download it before your subscription ends. Switch to Claude Go to claude.ai and upload your ChatGPT conversations. |
| BM25 | 2 | 0 | It is off-topic or does not materially answer the comparison. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| BM25 | 3 | 0 | It is off-topic or does not materially answer the comparison. | Programming has just become me dumping code and specs into Gemini, Claude, or ChatGPT, and then debugging whatever wrong stuff the AI spi... |
| BM25 | 4 | 0 | It is off-topic or does not materially answer the comparison. | At first, LLMs were quite bad so I didn’t really get any solutions out of them when problems got even slightly harder. However, Claude is... |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | We do have an enterprise subscription to Claude and ChatGPT at work for all the devs, but we have a strict rule that you shouldn't copy c... |
| BM25 | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Absolutely no pressure to do so, appreciate all the comments and support 🙏 You can read the free newsletter [here](https://nofil.beehiiv.... |
| BM25 | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | honestly after using claude daily for months through claude code, the biggest difference vs other models isnt the writing style — its how... |
| BM25 | 8 | 2 | It directly compares the requested models and gives a clear preference. | But Claude blew ChatGPT’s writing out of the water |
| BM25 | 9 | 2 | It directly compares the requested models and gives a clear preference. | Also, I prefer polishing my seo content in claude compared to chatgpt, claude feels more human in the way it writes stuff |
| BM25 | 10 | 0 | It is off-topic or does not materially answer the comparison. | Senior/Staff level dev with 15 years of experience and I’m just starting to get there with AI. I mostly use Claude within VS Code to prom... |
| BM25 | 11 | 0 | It is off-topic or does not materially answer the comparison. | It's scraping the live web rather than relying on training weights, which explains the divergence. 2. **Claude is the most conservative.*... |
| BM25 | 12 | 0 | It is off-topic or does not materially answer the comparison. | I asked the rational of getting everyone in the office access to Claude, OpenAI, Google and Meta and they said 'We're all in on AI here'. |
| BM25 | 13 | 0 | It is off-topic or does not materially answer the comparison. | I'm trying to say that with a low authority domain (i.e. mine) - I can rank in the same day because QFO's actually are longer tail. so -... |
| BM25 | 14 | 2 | It directly compares the requested models and gives a clear preference. | For your listicles specifically, chaining prompts across models can work well. Get ChatGPT 5.4 Thinking to build the outline, pass it to... |
| BM25 | 15 | 2 | It directly compares the requested models and gives a clear preference. | No single model is perfect at everything. ChatGPT might explain things clearly, Gemini might catch factual gaps, and Claude might synthes... |
| BM25 | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Then I use general purpose AI like ChatGPT or Claude AI for various tasks needing online sources. |
| BM25 | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | auto-generated content can work but honestly most SaaS founders are optimizing for the wrong thing getting pages indexed is step one. get... |
| BM25 | 18 | 1 | It mentions the requested models or theme but only partially answers the comparison. | With **nearly 3 billion searches now happening on AI platforms daily**, your goal shouldn't just be 'ranking' in Claude or ChatGPT—it sho... |
| BM25 | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Don’t rely on ChatGPT to do your keyword research. Use a keyword research tool, Mangools is pretty cheap and easy to use for a beginner. |
| BM25 | 20 | 0 | It is off-topic or does not materially answer the comparison. | And even when i finally shipped, either a competitor had already launched something similar or one of the big AI companies dropped an upd... |
| Hybrid | 1 | 2 | It directly compares the requested models and gives a clear preference. | I’ve noticed the same. ChatGPT tends to give better SEO structure and creative suggestions, while Claude is decent for longer text editing. |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Gemini is about as good as ChatGPT currently. I'm subbed to Claude and Gemini. |
| Hybrid | 3 | 0 | It is off-topic or does not materially answer the comparison. | Claude is better at coding diagnostics (sometimes) but yeah ChatGPT is overall better in this line of work for a lot |
| Hybrid | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Same. For coding Claude is better than GPT. |
| Hybrid | 5 | 0 | It is off-topic or does not materially answer the comparison. | ChatGPT needs lot of default prompting to make the output concise and serious. |
| Hybrid | 6 | 0 | It is off-topic or does not materially answer the comparison. | ChatGPT is still the generalist king, but it's been behind on coding since Claude 3.7 came out. |
| Hybrid | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Claude definitely seems to be more geared towards code, and it seems to do better with some code over others. |
| Hybrid | 8 | 2 | It directly compares the requested models and gives a clear preference. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |
| Hybrid | 9 | 2 | It directly compares the requested models and gives a clear preference. | I find chatgpt’s writing style very formal and clear. It uses proper grammar, punctuation, and vocabulary. |
| Hybrid | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | IMO, I feel Claude is over-hyped for SEO. Most of the output I've seen from content writers and SEOs still reads boring, just as what I'v... |
| Hybrid | 11 | 0 | It is off-topic or does not materially answer the comparison. | ChatGPT is such a pleaser. It's drive to be helpful overpowers it's limited understanding. |
| Hybrid | 12 | 0 | It is off-topic or does not materially answer the comparison. | With **nearly 3 billion searches now happening on AI platforms daily**, your goal shouldn't just be 'ranking' in Claude or ChatGPT—it sho... |
| Hybrid | 13 | 0 | It is off-topic or does not materially answer the comparison. | But Claude blew ChatGPT’s writing out of the water |
| Hybrid | 14 | 2 | It directly compares the requested models and gives a clear preference. | This happens with both ChatGPT and Claude. All AI is still a massive engineering problem with what they're trying to do. |
| Hybrid | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It's scraping the live web rather than relying on training weights, which explains the divergence. 2. **Claude is the most conservative.*... |
| Hybrid | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | My thoughts are that Claude-4-sonnet is really good and way better than chatgpt 4. |
| Hybrid | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Working static or WordPress? I keep ChatGPT on ideation - clustering, title/meta variants with reasoning - and use Claude for long-form r... |
| Hybrid | 18 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Also, I prefer polishing my seo content in claude compared to chatgpt, claude feels more human in the way it writes stuff |
| Hybrid | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | After my week of usage...I think chatgpt requires a lot of work to be of any practical use.... |
| Hybrid | 20 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Ask ChatGPT |

### Which AI hallucinates the most

- Category: `comparative`
- Winner: `hybrid`
- Rationale: Hybrid is much more on-target for hallucination, with multiple explicit hallucination statements near the top, while BM25 mostly finds broader AI-wrong or AI-fraud discussion.
- BM25 diagnostics: mode=lexical, response_ms=58.14, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2185.74, lexical_hits=100, vector_hits=200, fused_hits=298, reranked_hits=50, intent=semantic, alpha=0.3, beta=0.7
- Score@20: BM25 4 vs Hybrid 18 (delta +14)
- Relevant@20: BM25 4 vs Hybrid 15 (delta +11)
- Highly relevant@20: BM25 0 vs Hybrid 3 (delta +3)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 2, '6-10': 0, '11-20': 2} | Hybrid {'1-5': 5, '6-10': 5, '11-20': 8}
- Relevant overlap: 0 shared, 15 hybrid-only, 4 BM25-only
- Hybrid-only relevant examples: r7: AI can be right.; r19: AI did this 😂; r11: AI doesn’t hallucinate as much as two years ago.
- BM25-only relevant examples: r19: It seems to me that harder problems are more hallucination-prone, which is why it would make sense to limit what the...; r2: That seems the most plausible, essentially penetrating through a half assed AI coded banking assignment Also it was b...; r14: there's nothing to master...like... read the post. the AI supposedly did everything itself lol i get the anxiety and...
- Spot checks: Hybrid ranks 1, 6, and 15 are explicit hallucination statements that match the query intent.; BM25 has some relevant lines, but many entries are only loosely related to hallucination rather than directly about it.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | It mentions the requested models or theme but only partially answers the comparison. | You can vibe code a few lines at a time, but you need to know which ones the AI is wrong about, you need to break the task down for it, a... |
| BM25 | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | That seems the most plausible, essentially penetrating through a half assed AI coded banking assignment Also it was banking which has rel... |
| BM25 | 3 | 0 | It is off-topic or does not materially answer the comparison. | Be glad you can look at videos and tv or whatever you look at and can still spot AI here and there, and know that most videos you see are... |
| BM25 | 4 | 0 | It is off-topic or does not materially answer the comparison. | When I see a red flag, I call it out, I report it to security and my boss which turns into a meeting, which turns into a debate, lots of... |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | Google putting limit on how much it can show me and also doing so called 'intelligent' search which hurts results even more because I wan... |
| BM25 | 6 | 0 | It is off-topic or does not materially answer the comparison. | That is one of the things which still needs the most work when generating AI Art. |
| BM25 | 7 | 0 | It is off-topic or does not materially answer the comparison. | I'm going to be honest, if you asked me in 2020/2021 which is when they commented on this, when we'll have a working text to video genera... |
| BM25 | 8 | 0 | It is off-topic or does not materially answer the comparison. | GitHub repo with full instructions and a demo video: [https://github.com/TheBlewish/Automated-AI-Web-Researcher-Ollama](https://github.co... |
| BM25 | 9 | 0 | It is off-topic or does not materially answer the comparison. | I don't know what is going on in the industry that no recognition is being given to this subject. Most SWE's should be logical people so... |
| BM25 | 10 | 0 | It is off-topic or does not materially answer the comparison. | Users who don’t would create their own problems with or without AI. |
| BM25 | 11 | 0 | It is off-topic or does not materially answer the comparison. | Lately, I've started to do the opposite, which I'm sure the AI bros would balk at: I use the LLM to generate the plan, and I do the imple... |
| BM25 | 12 | 0 | It is off-topic or does not materially answer the comparison. | This was the board doing its duty to the mission of the nonprofit, which is to make sure that OpenAl builds AGI that benefits all of huma... |
| BM25 | 13 | 0 | It is off-topic or does not materially answer the comparison. | > But they're beholden to an authoritarian government that has committed human rights violations, has behaved aggressively on the world s... |
| BM25 | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | there's nothing to master...like... read the post. the AI supposedly did everything itself lol i get the anxiety and feeling the need to... |
| BM25 | 15 | 0 | It is off-topic or does not materially answer the comparison. | Because their government defined AI Research as a core pillar of their "new generation ai development plan for 2030" strategy, which they... |
| BM25 | 16 | 0 | It is off-topic or does not materially answer the comparison. | Creating useful organisms would first require AI design of proteins which we've yet to crack. |
| BM25 | 17 | 0 | It is off-topic or does not materially answer the comparison. | The thing is, most people wouldn't notice. It's like when you see these ridiculous images and videos which are clearly AI, but get loads... |
| BM25 | 18 | 0 | It is off-topic or does not materially answer the comparison. | People continue to look for things to get angry about, now they’ve moved on to claiming the Developers AI note is a lie and the AI hasn’t... |
| BM25 | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It seems to me that harder problems are more hallucination-prone, which is why it would make sense to limit what the model even attempts... |
| BM25 | 20 | 0 | It is off-topic or does not materially answer the comparison. | Karpathy posted about it which is how most people found out. the crazy part is the attackers code had a bug that caused a fork bomb and c... |
| Hybrid | 1 | 2 | It directly compares the requested models and gives a clear preference. | AI hallucinates on even very simple tasks I give it. |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | “AI Powered” so expect AI hallucinated heart attacks? |
| Hybrid | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Hallucinate mo bettah, AI. |
| Hybrid | 4 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Well if AI says so… |
| Hybrid | 5 | 0 | It is off-topic or does not materially answer the comparison. | AI? |
| Hybrid | 6 | 2 | It directly compares the requested models and gives a clear preference. | This is great until AI "hallucinates" a drug that kills thousands |
| Hybrid | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI can be right. |
| Hybrid | 8 | 0 | It is off-topic or does not materially answer the comparison. | Could be AI |
| Hybrid | 9 | 1 | It mentions the requested models or theme but only partially answers the comparison. | The problem isn't AI as a tool it's people telling you how to do your job and quoting hallucinations as proof that you're wrong. |
| Hybrid | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | All AI outputs are hallucination, they're just increasing correlation with reality. |
| Hybrid | 11 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI doesn’t hallucinate as much as two years ago. |
| Hybrid | 12 | 0 | It is off-topic or does not materially answer the comparison. | AI can do that as well though. |
| Hybrid | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I'm already stupid. If it weren't for AI, I'd get 100% wrong answers instead of 40% hallucinations lmfao |
| Hybrid | 14 | 0 | It is off-topic or does not materially answer the comparison. | just like AI |
| Hybrid | 15 | 2 | It directly compares the requested models and gives a clear preference. | In AI what you experienced is a “hallucination” and it’s pretty dangerous. |
| Hybrid | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | This isn't what hallucination is. This is another good example of how different AI memory and human memory is. |
| Hybrid | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Yup, I mean that's widely known. We also hallucinate a lot. Would like someone to measure average human hallucination rate between regula... |
| Hybrid | 18 | 0 | It is off-topic or does not materially answer the comparison. | > Slowly, day by day, the AI hype is dying dream on... Sure, most predictions are dumb and ridiculous, but AI is not going away. |
| Hybrid | 19 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI did this 😂 |
| Hybrid | 20 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Auto reply back with this - https://www.ibm.com/think/topics/ai-hallucinations |

### Best AI assistant for productivity

- Category: `comparative`
- Winner: `hybrid`
- Rationale: Hybrid gives a more direct productivity-assistant answer up front and keeps practical productivity advice in the top ranks, whereas BM25 leans more heavily on studies and adjacent commentary.
- BM25 diagnostics: mode=lexical, response_ms=60.51, lexical_hits=73, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=4443.8, lexical_hits=73, vector_hits=199, fused_hits=267, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 14 vs Hybrid 19 (delta +5)
- Relevant@20: BM25 10 vs Hybrid 15 (delta +5)
- Highly relevant@20: BM25 4 vs Hybrid 4 (delta +0)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 4, '6-10': 4, '11-20': 6} | Hybrid {'1-5': 5, '6-10': 2, '11-20': 12}
- Relevant overlap: 0 shared, 15 hybrid-only, 10 BM25-only
- Hybrid-only relevant examples: r7: . - wispr flow / superwhisper style apps: much more modern feeling. great if you like the ai-assisted vibe. i mostly...; r5: AI gives me the opportunity to actually accomplish something next to my programming job and hobbies.; r1: ai helps most with speed on small repetitive tasks. research summaries, rough drafts, quick prototypes. the gap is st...
- BM25-only relevant examples: r8: **The difference is stupid:** BEFORE: "Write a sales email" >*ChatGPT vomits generic template that screams AI* AFTER:...; r1: Anthropic: AI assisted coding doesn't show efficiency gains and impairs developers abilities.; r2: First line of the paper's abstract: >AI assistance produces significant productivity gains...
- Spot checks: Hybrid ranks 1, 11, 12, and 19 are strongly aligned with productivity use cases.; BM25 is relevant, but its best hits are more about studies or broader productivity debates than a practical assistant recommendation.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | It directly compares the requested models and gives a clear preference. | Anthropic: AI assisted coding doesn't show efficiency gains and impairs developers abilities. |
| BM25 | 2 | 2 | It directly compares the requested models and gives a clear preference. | First line of the paper's abstract: >AI assistance produces significant productivity gains... |
| BM25 | 3 | 0 | It is off-topic or does not materially answer the comparison. | The ASI they will get to will be for use in their products only. |
| BM25 | 4 | 0 | It is off-topic or does not materially answer the comparison. | I am a teaching assistant in one of the most competitive programs in my country and we recently had a student (who is supposed to be amon... |
| BM25 | 5 | 0 | It is off-topic or does not materially answer the comparison. | 20+ years in tech, and here's the one thing I'd tell every new programmer — I've written production code in everything from C to Rust to... |
| BM25 | 6 | 0 | It is off-topic or does not materially answer the comparison. | Collaborating with cross-functional teams in marketing, development, and product, you will shape strategies and infuse SEO best practices... |
| BM25 | 7 | 0 | It is off-topic or does not materially answer the comparison. | Most of the AI hype on the business side is just shoehorning in a ChatGPT wrapper into the product out of FOMO. |
| BM25 | 8 | 1 | It mentions the requested models or theme but only partially answers the comparison. | **The difference is stupid:** BEFORE: "Write a sales email" >*ChatGPT vomits generic template that screams AI* AFTER: "Write a sales emai... |
| BM25 | 9 | 2 | It directly compares the requested models and gives a clear preference. | The actual study / Anthropic's own blog on this is a more objective summary than the clickbait headline here: [https://www.anthropic.com/... |
| BM25 | 10 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I Created an AI Research Assistant that actually DOES research! |
| BM25 | 11 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I suspect we’re going to see a lot of games use this to make npc’s more natural \[[Link](https://twitter.com/Jenstine/status/164273279565... |
| BM25 | 12 | 2 | It directly compares the requested models and gives a clear preference. | We conduct randomized experiments to study how developers gained mastery of a new asynchronous programming library with and without the a... |
| BM25 | 13 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Slashing salary budgets and claiming AI is doing the work. I personally believe AI will be a nifty productivity assist and their dreams o... |
| BM25 | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | It’s an early legal milestone in the [fast-moving field of agentic commerce]( in which AI assistants browse, compare and buy products on... |
| BM25 | 15 | 0 | It is off-topic or does not materially answer the comparison. | Don’t destroy your brand perception by being careless. The best use case for AI right now is in product photography and B-roll shots. |
| BM25 | 16 | 0 | It is off-topic or does not materially answer the comparison. | And, as you've already observed with your peers, letting the AI spit something out you can't understand and putting it in production is j... |
| BM25 | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Over time, with practice and perseverance, your abilities catch up with your taste, and that's when you start to create great work. In th... |
| BM25 | 18 | 0 | It is off-topic or does not materially answer the comparison. | Imagine you're a person who has a problem that your product will solve, and go try to find one. Look at the nature of the results - AI ov... |
| BM25 | 19 | 0 | It is off-topic or does not materially answer the comparison. | My role has naturally skewed toward branding, product development, and marketing. I do enjoy the creative side - positioning, storytellin... |
| BM25 | 20 | 0 | It is off-topic or does not materially answer the comparison. | honestly the first \~50 for me came from just being in communities where my target users already hang out. im building an AI email tool a... |
| Hybrid | 1 | 2 | It directly compares the requested models and gives a clear preference. | ai helps most with speed on small repetitive tasks. research summaries, rough drafts, quick prototypes. the gap is still reliability, you... |
| Hybrid | 2 | 1 | It mentions the requested models or theme but only partially answers the comparison. | That’s great. i think that ai is a productivity booster for some people, like you. |
| Hybrid | 3 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Those who use AI to boost productivity will replace those who don't use AI tools. |
| Hybrid | 4 | 0 | It is off-topic or does not materially answer the comparison. | AI can do that as well though. |
| Hybrid | 5 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI gives me the opportunity to actually accomplish something next to my programming job and hobbies. |
| Hybrid | 6 | 1 | It mentions the requested models or theme but only partially answers the comparison. | The multi-step pipeline is clever, but I think it's treating the symptom rather than the cause. The reason AI-generated apps break in pro... |
| Hybrid | 7 | 1 | It mentions the requested models or theme but only partially answers the comparison. | . - wispr flow / superwhisper style apps: much more modern feeling. great if you like the ai-assisted vibe. i mostly see them fit best wh... |
| Hybrid | 8 | 0 | It is off-topic or does not materially answer the comparison. | Afterwards, I recommended also taking a look at other frameworks like [Vue](https://primevue.org/) or even just [htmx](https://htmx.org/)... |
| Hybrid | 9 | 0 | It is off-topic or does not materially answer the comparison. | AI is pretty good at simple CRUD tasks like this, but will struggle at something more advanced. |
| Hybrid | 10 | 0 | It is off-topic or does not materially answer the comparison. | Never allow AI to directly write a production system without user approval. |
| Hybrid | 11 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI is best for: * Completing tedious tasks that you know how to do * Guiding you through something you are learning * Asking for blind sp... |
| Hybrid | 12 | 2 | It directly compares the requested models and gives a clear preference. | The biggest edge I’ve seen isn’t a specific tool but using AI to remove small repetitive tasks (research, summaries, quick prototypes). |
| Hybrid | 13 | 2 | It directly compares the requested models and gives a clear preference. | Look at it this way, if it’s a task that an AI can do, then it is really work you want to do? |
| Hybrid | 14 | 1 | It mentions the requested models or theme but only partially answers the comparison. | Try asking AI |
| Hybrid | 15 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I Created an AI Research Assistant that actually DOES research! |
| Hybrid | 16 | 1 | It mentions the requested models or theme but only partially answers the comparison. | First line of the paper's abstract: >AI assistance produces significant productivity gains... |
| Hybrid | 17 | 1 | It mentions the requested models or theme but only partially answers the comparison. | AI is just a tool. It can help junior employees do their work faster but replace hmmm... not really |
| Hybrid | 18 | 1 | It mentions the requested models or theme but only partially answers the comparison. | I love AI! I use it to program the things I don't enjoy (work) so I have more time to code my side projects:)) |
| Hybrid | 19 | 2 | It directly compares the requested models and gives a clear preference. | Use AI like you use IDE. Learn the features, and use it to make your life easier, but put in the work. |
| Hybrid | 20 | 0 | It is off-topic or does not materially answer the comparison. | . > > 100%, it's "let's use AI" and not "here's a specific problem we think AI could help with" just the worst way to approach problems. |

### ChatGPT accuracy issues

- Category: `aspect`
- Winner: `hybrid`
- Rationale: Hybrid wins because its top ranks directly discuss ChatGPT being wrong, inaccurate, or confidently false, while BM25 mostly surfaces broader ChatGPT complaints with only weak accuracy focus.
- BM25 diagnostics: mode=lexical, response_ms=21.15, lexical_hits=2, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2493.9, lexical_hits=2, vector_hits=200, fused_hits=202, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 2 vs Hybrid 26 (delta +24)
- Relevant@20: BM25 2 vs Hybrid 18 (delta +16)
- Highly relevant@20: BM25 0 vs Hybrid 8 (delta +8)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 2, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 7, '6-10': 6, '11-20': 13}
- Relevant overlap: 1 shared, 17 hybrid-only, 1 BM25-only
- Hybrid-only relevant examples: r5: According to chatGPT, It doesn't learn from the conversations.; r4: Ask ChatGPT; r20: ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence.
- BM25-only relevant examples: r1: This is painfully common. The issue usually isn’t AI itself it’s how it’s rolled out.
- Spot checks: Hybrid front-loads accuracy and factuality complaints; BM25 is mostly adjacent ChatGPT chatter.; The best hybrid results are clearly closer to the intent than the BM25 pair.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | This is about general AI rollout pain and only indirectly touches ChatGPT accuracy. | This is painfully common. The issue usually isn’t AI itself it’s how it’s rolled out. |
| BM25 | 2 | 1 | This is a ChatGPT mention about data leakage, not a direct accuracy complaint. | The myth is that if my employee inputs sensitive data (IP, PII, etc.) into ChatGPT, then a threat actor or competitor on the other end mi... |
| Hybrid | 1 | 2 | This directly states ChatGPT is optimized for politeness rather than factual accuracy. | ChatGPT is designed for agreeability and politeness, not honesty or factual accuracy. |
| Hybrid | 2 | 1 | This only questions the ChatGPT connection and does not address accuracy itself. | What does that have to do with chatgpt? |
| Hybrid | 3 | 2 | This explicitly says ChatGPT is intended to provide accurate and reliable responses. | Some users appreciate the convenience of being able to get answers to their questions quickly, while others enjoy the novelty of interact... |
| Hybrid | 4 | 1 | This is a generic prompt mention of ChatGPT rather than an accuracy judgment. | Ask ChatGPT |
| Hybrid | 5 | 1 | This is about ChatGPT learning behavior, which is only indirectly related to accuracy. | According to chatGPT, It doesn't learn from the conversations. |
| Hybrid | 6 | 1 | This compares GPT-4 API quality, but it is still only loosely tied to accuracy. | That's a chatgpt specific problem. Gpt 4 from the API isn't that bad, neither are the rest of the chatbots from providers that are not Op... |
| Hybrid | 7 | 1 | This says familiarity with the subject matters, which is relevant but indirect. | The key with chatGPT (imo) is to at least be familiar with the subject information. |
| Hybrid | 8 | 1 | This mentions flaws and security issues, but not accuracy specifically. | News of recent flaws and security issues with ChatGPT |
| Hybrid | 9 | 2 | This says ChatGPT is designed to stick closer to objective truths. | This is a program that is trained to give well composed answers given the prompt. I understand that ChatGPT with GPT 4 addresses this iss... |
| Hybrid | 10 | 1 | This is a data-leakage myth discussion, not an accuracy complaint. | The myth is that if my employee inputs sensitive data (IP, PII, etc.) into ChatGPT, then a threat actor or competitor on the other end mi... |
| Hybrid | 11 | 2 | This says ChatGPT is confidently wrong, which is directly on query. | width=1510&format=pjpg&auto=webp&s=0917e41fa99e99a4f32c0e78f71059b3f9fe2e65 It gave me the error each time. ChatGPT is so confident in this. |
| Hybrid | 12 | 1 | This says the user had no issues, so it is only weakly relevant. | I've talked/interactive with chatGPT for over 8 hours before, and used the same "context instance" for a couple of days and have not had... |
| Hybrid | 13 | 2 | This says ChatGPT kept giving wrong information and apologizing. | Recent chat I had with chatgpt, It kept giving the wrong information and then would apologize when I correct it. |
| Hybrid | 14 | 2 | This explicitly calls ChatGPT fluent bullshit and emphasizes fact-checking. | I love how some people commented: ChatGPT is just fluent bullshit. And fact checking those is hard. |
| Hybrid | 15 | 1 | This mentions ChatGPT issues, but the snippet is too vague to be strongly diagnostic. | I asked ChatGPT and it gave me its issues. I asked further because it felt somewhat familiar: https://preview.redd.it/jom498m7yt0f1.jpeg? |
| Hybrid | 16 | 0 | This is about conversions, not ChatGPT accuracy. | Very low - however, the important question is what conversions are you getting from ChatGPT. Not many people are tracking this, but I bet... |
| Hybrid | 17 | 2 | This directly says ChatGPT is often confidently wrong, which matches the query. | I like AI, but this is entirely reasonable. ChatGPT is often confidently wrong, which is quite dangerous to have when you're looking for... |
| Hybrid | 18 | 0 | This is an analogy about a boss and is not about accuracy. | Your chatGPT is like the typical boss. employee: „hey boss, I think we should do A“. |
| Hybrid | 19 | 1 | This says ChatGPT can be fantastic for some tasks, which is only weakly relevant. | I think you guys are just not very good and reading and can't tell that I was agreeing. >The things I use ChatGPT for, it does a fantasti... |
| Hybrid | 20 | 2 | This explicitly says ChatGPT is frequently wrong with calm confidence. | ChatGPT is absolutely excellent. But it is frequently wrong, and it's wrong with calm and assured confidence. |

### Claude safety vs usefulness

- Category: `aspect`
- Winner: `bm25`
- Rationale: BM25 wins because it keeps the top ranks anchored to Claude safety, caution, and practical use cases, while hybrid starts with weaker keyword-only material before reaching the substantive Claude evidence.
- BM25 diagnostics: mode=lexical, response_ms=48.32, lexical_hits=28, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=4403.15, lexical_hits=28, vector_hits=196, fused_hits=220, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 35 vs Hybrid 34 (delta -1)
- Relevant@20: BM25 19 vs Hybrid 18 (delta -1)
- Highly relevant@20: BM25 16 vs Hybrid 16 (delta +0)
- First relevant rank: BM25 1 | Hybrid 2
- Band totals: BM25 {'1-5': 8, '6-10': 8, '11-20': 19} | Hybrid {'1-5': 8, '6-10': 8, '11-20': 18}
- Relevant overlap: 0 shared, 18 hybrid-only, 18 BM25-only
- Hybrid-only relevant examples: r12: Claude 4.0 was down at work today and I had to downgrade to 3.7 Legitimately unusable by comparison, nothing it produ...; r11: Claude is a best and you're not limited (unless you run out of tokens/prompts) Hmu if you need a hand optimising your...; r17: Claude is great at unfucking code if you have already built those skills
- BM25-only relevant examples: r1: **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clar...; r4: After building agents for 2 years, I stopped using function calling entirely. Here's what I use instead.; r15: Don't send your key to anyone or enter it online anywhere, the AI tools can generate a complete offline script, use i...
- Spot checks: BM25 is more focused on the safety-versus-utility tradeoff in the top ranks.; Hybrid is relevant overall, but the first result is too weak to beat BM25 on ranking quality.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | This mentions Claude in a prompt example, but it is not really about safety or usefulness. | **What I need to know:** - **Target AI:** ChatGPT, Claude, Gemini, or Other - **Prompt Style:** DETAIL (I'll ask clarifying questions fir... |
| BM25 | 2 | 2 | This is about deploying AI in regulated settings, which is directly relevant to safety. | Lessons from deploying RAG bots for regulated industries Built a RAG-powered AI assistant for Australian workplace compliance use cases.... |
| BM25 | 3 | 2 | This is explicitly about Anthropic's safety work around Claude. | We’ve officially hit the point where AI isn’t just helping attackers, it’s running the show. Anthropic (the AI safety company behind Clau... |
| BM25 | 4 | 1 | This is about AI agents and function calling, which is only indirectly related. | After building agents for 2 years, I stopped using function calling entirely. Here's what I use instead. |
| BM25 | 5 | 2 | This directly contrasts restricted use versus broader useful use. | Given the choice between being required to blindly use it for everything, vs not being allowed to use it beyond research, I would happily... |
| BM25 | 6 | 0 | This is unrelated to Claude safety or usefulness. | Written and collated entirely by me, no chatgpt used) |
| BM25 | 7 | 2 | This describes Claude following complex instructions well, which is directly about usefulness. | honestly after using claude daily for months through claude code, the biggest difference vs other models isnt the writing style — its how... |
| BM25 | 8 | 2 | This references constitutional AI feedback used to train Claude, which is safety-relevant. | It also optionally generates feedback and reasoning for why the response is good, okay, or bad, so you can use it as a source of consiste... |
| BM25 | 9 | 2 | This says the user mostly uses Claude for features and diagnosis, which is directly useful. | Senior/Staff level dev with 15 years of experience and I’m just starting to get there with AI. I mostly use Claude within VS Code to prom... |
| BM25 | 10 | 2 | This discusses Claude in safety-critical systems, which is directly relevant. | I’m a senior dev with 9 year experience who works in more traditional SW development (C++ development in Linux for use in safety critical... |
| BM25 | 11 | 2 | This describes building documentation with Claude, which is clearly useful. | I’m not a dev anymore, I handle project implementations for our business now, so I’ve built myself a tool in VS Code using Claude which c... |
| BM25 | 12 | 2 | This says Claude helps review PRs, which is directly useful. | I'm currently using Qwen3.5-27b at IQ4\_XS through llama.cpp and Qwen Code Companion in VS Code (with a 3090) to do planning and implemen... |
| BM25 | 13 | 2 | This says Claude is conservative and discusses presence rates, which is relevant to safety. | It's scraping the live web rather than relying on training weights, which explains the divergence. 2. **Claude is the most conservative.*... |
| BM25 | 14 | 2 | This describes a Claude agent built into VS Code for codebase use, which is useful. | For contrast, my company implemented a Claude agent trained on our codebase (massive FAANG company) which is built into VS Code. |
| BM25 | 15 | 2 | This gives a concrete safety tip about keys and airgapped use. | Don't send your key to anyone or enter it online anywhere, the AI tools can generate a complete offline script, use it on an airgapped ma... |
| BM25 | 16 | 2 | This is explicitly about workflow and safety expectations. | I’m less interested in “AI hype” and more in workflow + safety: what permissions are acceptable, what guardrails you’d expect, and what i... |
| BM25 | 17 | 2 | This compares structured prompting and Claude Code performance, which is usefulness-related. | the structured prompting vs vibe coding distinction is so real. i use claude code with opus daily and for loose prompts the gap is massiv... |
| BM25 | 18 | 2 | This repeats Claude usefulness in coding workflows. | the structured prompting vs vibe coding distinction is so real. i use claude code with opus daily and for loose prompts the gap is massiv... |
| BM25 | 19 | 2 | This says Claude plus Windsurf is worth trying, which is directly useful. | If you're worried about AI, I mean the best way to alleviate that fear is just try leaning into it. I use Claude + Windsurf on side proje... |
| BM25 | 20 | 1 | This mentions Claude reliability, but the safety/usefulness connection is weaker than the other results. | I also look for inconsistencies: like „fully hosted in Germany“ vs „Opt for renowned alternatives like Google’s PaLM2, OpenAI’s GPT-4, or... |
| Hybrid | 1 | 0 | This is just a bare keyword result and does not add meaningful safety or usefulness evidence. | Claude |
| Hybrid | 2 | 2 | This directly says Claude is overly censored, which is relevant to the safety versus usefulness tradeoff. | Claude is overly censored and feels like it was created for people living in a police state, it's only really good for coding. |
| Hybrid | 3 | 2 | This says Claude is a powerhouse in the right hands, which is directly about usefulness. | Only evidence I can give is anecdotal but Claude is absolutely a powerhouse in the right hands. |
| Hybrid | 4 | 2 | This describes using Claude over AWS Bedrock with security boundary constraints, which is directly relevant. | One of the thing Claude is absolutely best at by a large margin is prompting other agents, because it has a better 'sense of self'. |
| Hybrid | 5 | 2 | This directly contrasts forced broad use with limited research use. | It can’t do video or image and isn’t a great shopping assistant. But Claude in excel is legitimately good, as is Claude code. |
| Hybrid | 6 | 0 | This is unrelated to Claude safety or usefulness. | Claude 4.0 is light years better than the original q which was literally worthless. |
| Hybrid | 7 | 2 | This says Claude follows complex instructions precisely, which is clearly useful. | Out of the box Claude is vanilla - you can customise depending on task at hand. |
| Hybrid | 8 | 2 | This references Claude-style feedback generation and safety-oriented evaluation. | Yet the security tool couldn’t find vulnerabilities in Claude Code itself. Very funny [ |
| Hybrid | 9 | 2 | This says the user mostly uses Claude inside VS Code for features and diagnosis. | Consistently going back a couple of years now I have just always noticed that Claude gives more useful responses no matter what I’m doing. |
| Hybrid | 10 | 2 | This is about Claude in safety-critical development, which is directly relevant. | Try Claude. |
| Hybrid | 11 | 2 | This describes building documentation and transcripts with Claude, which is useful. | Claude is a best and you're not limited (unless you run out of tokens/prompts) Hmu if you need a hand optimising your site with Claude..:) |
| Hybrid | 12 | 2 | This says Claude helps review PRs, which is directly useful. | Claude 4.0 was down at work today and I had to downgrade to 3.7 Legitimately unusable by comparison, nothing it produced was worthwhile. |
| Hybrid | 13 | 2 | This says Claude is the most conservative model, which is safety-relevant. | Or is this just not realistic yet? I am mostly a Claude Code user but, my attitude is, when Uber first came out I used it all the time. |
| Hybrid | 14 | 2 | This describes a Claude agent trained on a codebase, which is useful. | I've been bringing this up for quite some time now because it transforms Claude Cli into something useable with local models. |
| Hybrid | 15 | 2 | This is a concrete safety tip about offline scripts and airgapped use. | So it's basically just a tuned Claude wrapper? That was already my assumption. |
| Hybrid | 16 | 2 | This says the user cares about workflow and safety, which matches the query well. | Same. For coding Claude is better than GPT. |
| Hybrid | 17 | 2 | This compares structured prompting and Claude Code with debugging cycles, which is useful. | Claude is great at unfucking code if you have already built those skills |
| Hybrid | 18 | 2 | This says Claude plus Windsurf is good for side projects, which is useful. | Websites from Claude usually look similar if they haven’t been substantially edited. |
| Hybrid | 19 | 1 | This mentions reliability, but it is a weaker fit than the top Claude-focused results. | My company uses Claude over AWS Bedrock. Our code never leaves our internal network + AWS environment and security boundary. |
| Hybrid | 20 | 1 | This is about a general use case comparison and is only loosely tied to the query. | Given the choice between being required to blindly use it for everything, vs not being allowed to use it beyond research, I would happily... |

### Gemini performance problems

- Category: `aspect`
- Winner: `hybrid`
- Rationale: Hybrid wins because it surfaces many direct Gemini performance complaints, model comparisons, and usage problems in the top ranks, while BM25 only returns one clearly relevant item and one weak lead-in.
- BM25 diagnostics: mode=lexical, response_ms=23.22, lexical_hits=2, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2626.22, lexical_hits=2, vector_hits=196, fused_hits=197, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 2 vs Hybrid 24 (delta +22)
- Relevant@20: BM25 1 vs Hybrid 19 (delta +18)
- Highly relevant@20: BM25 1 vs Hybrid 5 (delta +4)
- First relevant rank: BM25 2 | Hybrid 1
- Band totals: BM25 {'1-5': 2, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 10, '6-10': 5, '11-20': 9}
- Relevant overlap: 1 shared, 18 hybrid-only, 0 BM25-only
- Hybrid-only relevant examples: r7: [Here]( is a post from someone whose funds are stuck on Gemini so I guess we could rate them at the bottom.; r19: For my areas of expertise, it's not capable of understanding much in the way of nuance but Gemini 3 Pro will give gen...; r4: Gemini 2.5 pro after 200k context is just so much worse and falls off hard.
- Spot checks: BM25 has almost no depth on the Gemini performance aspect.; Hybrid consistently returns Gemini-specific performance complaints and comparisons.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 0 | This is a generic startup comment and does not really address Gemini performance. | "this is annoying" and "i'd pay money to make this go away" are completely different things. people just shrug and move on. the discomfor... |
| BM25 | 2 | 2 | This is explicitly about a Gemini-powered performance analysis workflow. | System Stability and Performance Analysis. ⚙️ System Stability and Performance Intelligence A self‑service diagnostic workflow powered by... |
| Hybrid | 1 | 2 | This directly discusses Gemini 2.5 and pressure on performance. | R2 will put heavy pressure.more than Gemini 2.5 already does. |
| Hybrid | 2 | 2 | This is explicitly about a Gemini performance analysis workflow. | System Stability and Performance Analysis. ⚙️ System Stability and Performance Intelligence A self‑service diagnostic workflow powered by... |
| Hybrid | 3 | 2 | This is a direct Gemini UI troubleshooting example. | Gemini just helped me fix a very complicated UI issue in a react-native app where a bottom sheet position was being globally shared via c... |
| Hybrid | 4 | 2 | This says Gemini gets much worse after long context, which is directly on query. | Gemini 2.5 pro after 200k context is just so much worse and falls off hard. |
| Hybrid | 5 | 2 | This says Gemini does this with code, which is a direct performance complaint. | Gemini 2.5 pro does this sometimes with code. Will give a placeholder function and say a script is complete until I call it out. |
| Hybrid | 6 | 1 | This references Gemini 1.5 behavior, but the snippet is less explicit than the top complaints. | I tried with Gemini Pro 1.5 (latest) and thankfully, it didn't propose it. |
| Hybrid | 7 | 1 | This is about funds stuck on Gemini and only indirectly about the model. | [Here]( is a post from someone whose funds are stuck on Gemini so I guess we could rate them at the bottom. |
| Hybrid | 8 | 1 | This is a Gemini joke about burden and memory, which is only weakly relevant. | It's a burden for it to reply and try to find the answer deep in its neural networks. Gemini: "- Am I a slave to you?". |
| Hybrid | 9 | 1 | This mentions Gemini deep research and productivity, which is related but not a complaint. | Using a combination of Gemini deep research and open ai, I literally did two days worth of work in ten minutes before I got out of bed th... |
| Hybrid | 10 | 1 | This is a broad comparison that says Gemini stomped on other models, not a clear problem report. | Like seriously, HOW, how did OpenAI blow their lead so fucking hard, gemini just stomped on EVERY other model, definitely destroys sora i... |
| Hybrid | 11 | 1 | This discusses Gemini search intent, which is not really a performance problem. | Shaun Anderson made a very good point: Google and Gemini have search intent down. Website Squadron, therefore, uses Gemini Pro to get con... |
| Hybrid | 12 | 1 | This is a positive Gemini usage statement, not a problem report. | Gemini 2.5 Pro is my partner in big projects, consisting of Python code and animation discussions in Fusion. |
| Hybrid | 13 | 1 | This is a playful Gemini comment, but it still indicates direct usage context. | You can achieve all that by being 9 years old and collaborating with Gemini! |
| Hybrid | 14 | 1 | This is about Gemini ethics and anxiety claims, not performance. | This is absolutely hysterical on a surface level but Anthropic has indicated that AI are capable of experiencing anxiety and it makes the... |
| Hybrid | 15 | 1 | This is a general stack preference and not a performance issue. | I think a Claude/Gemini stack is perfect!!! OpenAI lost this race a while ago and I think yesterday was the final straw!!! |
| Hybrid | 16 | 1 | This is a Gemini availability-in-Google-apps comment, which is not a performance complaint. | I use Google for my business and Gemini is now in all Google apps to include Sheets, Slides, Gmail, Docs - it’s really incredible. |
| Hybrid | 17 | 1 | This is a hostile sentiment about Gemini, but it is not a clear performance issue. | Gemini is shit. Don’t ever trust those Harvard pricks. |
| Hybrid | 18 | 1 | This is about a Gemini version comparison, which is relevant but weakly stated. | I think Gemini-2.5-pro had them cornered. I will expect Gemini-3.0-pro to cement them. |
| Hybrid | 19 | 1 | This says Gemini Pro gives generally correct responses, which is positive and only loosely tied to problems. | For my areas of expertise, it's not capable of understanding much in the way of nuance but Gemini 3 Pro will give generally correct respo... |
| Hybrid | 20 | 0 | This is a name-origin comment and is not relevant to Gemini performance. | Gemini is lead by “Hassabis”, a name originating from “hisab”, which means “calculation” or “account”. |

### AI hallucination complaints

- Category: `aspect`
- Winner: `hybrid`
- Rationale: Hybrid wins because it retrieves a broader set of hallucination complaints and paraphrases, while BM25 is very precise but too shallow with only two visible results.
- BM25 diagnostics: mode=lexical, response_ms=22.82, lexical_hits=2, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2384.39, lexical_hits=2, vector_hits=200, fused_hits=202, reranked_hits=50, intent=keyword, alpha=0.8, beta=0.2
- Score@20: BM25 4 vs Hybrid 14 (delta +10)
- Relevant@20: BM25 2 vs Hybrid 10 (delta +8)
- Highly relevant@20: BM25 2 vs Hybrid 4 (delta +2)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 4, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 8, '6-10': 3, '11-20': 3}
- Relevant overlap: 0 shared, 10 hybrid-only, 2 BM25-only
- Hybrid-only relevant examples: r10: AI doesn’t hallucinate as much as two years ago.; r3: AI hallucinates on even very simple tasks I give it.; r5: All AI outputs are hallucination, they're just increasing correlation with reality.
- BM25-only relevant examples: r1: Biggest complaint? Hallucinations, for sure. And sometimes it's really confident while being totally wrong.; r2: Things like personality drift and hallucinations occur when AI models compact their context, but choose the wrong set...
- Spot checks: BM25 is high precision but low depth on hallucination complaints.; Hybrid adds more variety in how hallucination complaints are expressed.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | This directly names hallucinations as the biggest complaint and mentions confident wrong answers. | Biggest complaint? Hallucinations, for sure. And sometimes it's really confident while being totally wrong. |
| BM25 | 2 | 2 | This explicitly says hallucinations happen when context is compacted incorrectly. | Things like personality drift and hallucinations occur when AI models compact their context, but choose the wrong sets of tokens to discard. |
| Hybrid | 1 | 1 | This is about people citing hallucinations to criticize AI, which is related but indirect. | The problem isn't AI as a tool it's people telling you how to do your job and quoting hallucinations as proof that you're wrong. |
| Hybrid | 2 | 2 | This explicitly says hallucination in AI is dangerous. | In AI what you experienced is a “hallucination” and it’s pretty dangerous. |
| Hybrid | 3 | 2 | This directly says AI hallucinates on simple tasks. | AI hallucinates on even very simple tasks I give it. |
| Hybrid | 4 | 1 | This is only a brief AI/reality quip and is weakly relevant. | Well if AI says so… |
| Hybrid | 5 | 2 | This says all AI outputs are hallucination, which is directly on topic. | All AI outputs are hallucination, they're just increasing correlation with reality. |
| Hybrid | 6 | 1 | This references distinguishing AI from reality, which is only partially relevant. | For anyone who struggles to discern AI from reality, this image isn't real. |
| Hybrid | 7 | 0 | This is a reaction image-style comment and is not substantive. | AI did this 😂 |
| Hybrid | 8 | 1 | This explains what hallucination is not, which is still only partially relevant. | This isn't what hallucination is. This is another good example of how different AI memory and human memory is. |
| Hybrid | 9 | 0 | This is a generic AI insult and not a hallucination complaint. | AI, need I say more? |
| Hybrid | 10 | 1 | This says hallucinations are less frequent than before, which is related but not a complaint. | AI doesn’t hallucinate as much as two years ago. |
| Hybrid | 11 | 0 | This is a generic insult and not about hallucinations. | stupid ai |
| Hybrid | 12 | 0 | This complains about AI advertising, not hallucinations. | This is why AI is advertised so much. To make people even more stupid to belive whatever they say and do whatever they say. |
| Hybrid | 13 | 0 | This is about scheming or misbehavior, not hallucinations. | AI is like a self-driving car. It does awesome on a new well-built road, and no weird exceptions show up. once it hits something it's not... |
| Hybrid | 14 | 0 | This is just a joke about hallucination wording. | Hallucinate mo bettah, AI. |
| Hybrid | 15 | 0 | This is about real AI versus general AI terminology, not hallucinations. | At this point, we probably need to start using a new term for "real" (theoretical) AI to differentiate it from this stuff. I've seen peop... |
| Hybrid | 16 | 0 | This asks whether something is AI, which is not a hallucination complaint. | Is this AI? |
| Hybrid | 17 | 0 | This is a general anti-AI statement without hallucination content. | You have to understand what stuff is doing period. AI is a trap. |
| Hybrid | 18 | 1 | This refers to AI hallucinated heart attacks, which is related but brief. | “AI Powered” so expect AI hallucinated heart attacks? |
| Hybrid | 19 | 2 | This says AI makes things up all the time, which is directly about hallucinations. | People just assume that since AI gave them info that it's 100% true\\facts. It is in fact not, AI makes shit up all the time. |
| Hybrid | 20 | 0 | This is about criticizing AI methods, not hallucinations. | The big issue with the people using AI is when you question their methods, they ask AI how to resond to the criticism. |

### AI bias and fairness concerns

- Category: `aspect`
- Winner: `bm25`
- Rationale: BM25 wins because it keeps bias, fairness, ethics, and alignment concerns in the top ranks, while hybrid mostly drifts into generic AI chatter and off-topic Bitcoin noise.
- BM25 diagnostics: mode=lexical, response_ms=26.83, lexical_hits=5, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=2746.83, lexical_hits=5, vector_hits=200, fused_hits=205, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 7 vs Hybrid 3 (delta -4)
- Relevant@20: BM25 5 vs Hybrid 2 (delta -3)
- Highly relevant@20: BM25 2 vs Hybrid 1 (delta -1)
- First relevant rank: BM25 1 | Hybrid 11
- Band totals: BM25 {'1-5': 7, '6-10': 0, '11-20': 0} | Hybrid {'1-5': 0, '6-10': 0, '11-20': 3}
- Relevant overlap: 1 shared, 1 hybrid-only, 4 BM25-only
- Hybrid-only relevant examples: r11: Most AI is designed to please the user as opposed to give the best answer.
- BM25-only relevant examples: r5: >I just gave you way more Hindsight bias To be fair you need to pick random dates . Again , don't trust me , ask AI t...; r2: he answered: "I mean, fair, I agree that there is a not ideal element to it. 100%." https://twitter.com/AISafetyMemes...; r3: The CMA proposes the possibility for publishers to opt out of generative AI features in Google Search (AI Overview, A...
- Spot checks: The BM25 top five are all at least conceptually tied to bias, fairness, or ethics.; Hybrid mostly fails to stay on the bias/fairness aspect until very late in the ranking.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | This is about a teen suicide linked to an AI chatbot, which is more safety-related than bias-related. | The reference to a teen suicide linked to an AI chatbot is concerning, though I’d need to verify the details. |
| BM25 | 2 | 1 | This is about an AI safety report and is only indirectly related to fairness. | he answered: "I mean, fair, I agree that there is a not ideal element to it. 100%." https://twitter.com/AISafetyMemes/status/172571264211... |
| BM25 | 3 | 1 | This is about opt-outs for AI search features and is only weakly related to fairness. | The CMA proposes the possibility for publishers to opt out of generative AI features in Google Search (AI Overview, AI Mode). |
| BM25 | 4 | 2 | This directly references the alignment problem and oppressive societal structures. | The alignment problem is their great project—their attempt at making sure that we won't lose control and get terminated by robots. ### AI... |
| BM25 | 5 | 2 | This explicitly discusses hindsight bias and selection bias. | >I just gave you way more Hindsight bias To be fair you need to pick random dates . Again , don't trust me , ask AI to generate you 10 or... |
| Hybrid | 1 | 0 | This is just a bare AI mention and is not about bias or fairness. | AI? |
| Hybrid | 2 | 0 | This is a generic AI remark and not about bias or fairness. | Well if AI says so… |
| Hybrid | 3 | 0 | This is a capability comment, not a bias or fairness concern. | AI can do that as well though. |
| Hybrid | 4 | 0 | This is a generic AI statement, not a bias or fairness concern. | AI can be right. |
| Hybrid | 5 | 0 | This is about AI content spam, not bias or fairness. | I am pretty sure that shitty AI content is intentionally mass produced and shared so that people more easily miss the really good AI works. |
| Hybrid | 6 | 0 | This is a generic insult about AI and not about bias or fairness. | The purpose of AI is to make incompetent people difficult to ignore. |
| Hybrid | 7 | 0 | This blames a person rather than discussing AI bias or fairness. | Your issue isn't with AI, it's about this individual. He's acting unprofessional, not AI. |
| Hybrid | 8 | 0 | This is about decision-making quality, not bias or fairness. | You have to understand that a lot of decisions aren’t based on how good AI is. It just has to be good enough to convince the non-technica... |
| Hybrid | 9 | 0 | This is about model quality in general, not bias or fairness. | In the best case, your AI will be only as good as people programming/training it. |
| Hybrid | 10 | 0 | This is about responding to criticism, not bias or fairness. | The big issue with the people using AI is when you question their methods, they ask AI how to resond to the criticism. |
| Hybrid | 11 | 1 | This says AI is designed to please users rather than give the best answer, which is only loosely fairness-related. | Most AI is designed to please the user as opposed to give the best answer. |
| Hybrid | 12 | 0 | This is about not using AI at all, not bias or fairness. | I'm balancing it by not using AI at all. |
| Hybrid | 13 | 0 | This is just a generic AI remark. | AI, need I say more? |
| Hybrid | 14 | 0 | This is about AI as a tool and not about bias or fairness. | Reminder that AI can be a good tool for honest professionals and is not inherently bad. |
| Hybrid | 15 | 0 | This is a self-driving-car analogy about misbehavior, not bias. | AI is like a self-driving car. It does awesome on a new well-built road, and no weird exceptions show up. once it hits something it's not... |
| Hybrid | 16 | 0 | This is a generic danger statement with no bias angle. | AI can be very dangerous." The AI: |
| Hybrid | 17 | 0 | This asks about using AI and is not about bias or fairness. | And for that you used AI, why? |
| Hybrid | 18 | 0 | This is an anti-AI statement and not about bias or fairness. | You have to understand what stuff is doing period. AI is a trap. |
| Hybrid | 19 | 0 | This complains about non-technical decision makers, which is not directly bias-related. | My biggest gripe with AI is when people who are not well-versed in technology are allowed to make decisions concerning it. |
| Hybrid | 20 | 2 | This explicitly revisits the alignment problem and oppressive structures. | The alignment problem is their great project—their attempt at making sure that we won't lose control and get terminated by robots. ### AI... |

### AI impact on jobs

- Category: `aspect`
- Winner: `hybrid`
- Rationale: Hybrid wins because it keeps the entire top-20 tightly on AI and jobs, with clearer direct job-displacement framing at the top, while BM25 is strong but noisier and less focused in the early ranks.
- BM25 diagnostics: mode=lexical, response_ms=34.44, lexical_hits=14, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3343.45, lexical_hits=14, vector_hits=198, fused_hits=209, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 18 vs Hybrid 38 (delta +20)
- Relevant@20: BM25 13 vs Hybrid 20 (delta +7)
- Highly relevant@20: BM25 5 vs Hybrid 18 (delta +13)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 9, '6-10': 6, '11-20': 3} | Hybrid {'1-5': 10, '6-10': 10, '11-20': 18}
- Relevant overlap: 0 shared, 20 hybrid-only, 13 BM25-only
- Hybrid-only relevant examples: r14: AI is the reason why you need to work more. Your employer is getting bombarded by emails by experienced developers wh...; r3: AI itself won't take the jobs. If you haven't boosted your productivity yet using AI your falling behind.; r2: AI will bring more tech jobs, not less. Juniors will be supporting business people "vibe coding" and trying out busin...
- BM25-only relevant examples: r3: And the worlds fucking mental at the moment, and I'm aware of the environmental impact AI is having. The AI bubble, t...; r9: Embrace AI slop, don't have people have even basic training on best practices.; r10: Every Sunday, I carefully curate around 20 high-impact topics across the cybersecurity industry, including: 1.
- Spot checks: Hybrid is more consistently about AI replacing or reshaping jobs across the full ranking.; BM25 has some relevant items, but several top hits are broader labor or productivity commentary.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 1 | This is about US jobs and AI orders, which is relevant but not a direct AI job-impact discussion. | Trump tells tech companies to 'stop hiring Indians', signs new AI orders to focus on US jobs — https://www.indiaweekly.biz/trump-tells-te... |
| BM25 | 2 | 2 | This explicitly talks about future jobs and AI interfaces. | There are far far less paying jobs for future human AI interface lords than present day smart people. |
| BM25 | 3 | 2 | This directly mentions job replacements and AI's environmental impact. | And the worlds fucking mental at the moment, and I'm aware of the environmental impact AI is having. The AI bubble, the job replacements,... |
| BM25 | 4 | 2 | This says AI will affect jobs in finance, which is directly relevant. | s=20)\] * Build financial models with AI. Lots of jobs in finance at risk too \[[Link](https://twitter.com/ryankishore_/status/1641553735... |
| BM25 | 5 | 2 | This discusses AI as a productivity multiplier and its job effects. | I think there are 2 outcomes with this in the short term (5 years): 1. Ai tools act as a productivity multiplier, and more overall work g... |
| BM25 | 6 | 1 | This is about engineering abstraction and speed, only indirectly related to jobs. | I am not paid to do that because it impacts speed. So we write enough abstraction to do the job and we limp it along until it becomes too... |
| BM25 | 7 | 1 | This asks whether a corporate job is worth it in an AI world, which is relevant but indirect. | Would really appreciate perspectives from people who have: * stayed in early-stage startups vs. left * moved from entrepreneurship → stru... |
| BM25 | 8 | 2 | This asks about AI impacting software dev jobs, which is directly relevant. | Serious question but what is the outrage of AI impacting software dev jobs based on? For years software engineering has built solutions t... |
| BM25 | 9 | 1 | This says AI slop and training are a problem, which is only loosely job-related. | Embrace AI slop, don't have people have even basic training on best practices. |
| BM25 | 10 | 1 | This is a cybersecurity topic list and only weakly job-related. | Every Sunday, I carefully curate around 20 high-impact topics across the cybersecurity industry, including: 1. |
| BM25 | 11 | 1 | This asks about AI-enabled work and advantage, which is relevant but broad. | The drive for AI enabled work isn't going away. Can you turn that to your advantage? |
| BM25 | 12 | 1 | This is a marketing/analytics workflow comment and only indirectly about jobs. | I was In charge of my own analytics and KPIs and had to perform strong and prove quarterly/monthly what impacts my work has had. I lowkey... |
| BM25 | 13 | 1 | This mentions job-related scanning and threat modeling, but it is not really about AI jobs. | Or worse... circumvented by an employee that may have just been trying to do their job. Our scans show green. We're repeatable. We threat... |
| BM25 | 14 | 0 | This is about job boundaries and AI adoption, but the snippet does not directly address job impact. | IMO it's worth putting in the effort to put boundaries on this job if that'll address the issues you have with it because of course the j... |
| Hybrid | 1 | 2 | This directly says AI will replace jobs that do not require much thought. | ai will replace jobs that dont require much thought. when the ai gets better more jobs will be replaced. |
| Hybrid | 2 | 2 | This directly says AI will bring more tech jobs and shift work toward vibe coding. | AI will bring more tech jobs, not less. Juniors will be supporting business people "vibe coding" and trying out business ideas. |
| Hybrid | 3 | 2 | This says AI will not take the jobs, but productivity will matter more. | AI itself won't take the jobs. If you haven't boosted your productivity yet using AI your falling behind. |
| Hybrid | 4 | 2 | This directly says jobs are now taken by AI. | Those jobs are now taken by AI 😭 |
| Hybrid | 5 | 2 | This says AI proficiency will become a hiring requirement. | Every company will expect you to be able to use ai to code and if you aren’t as fast as your peers are with it, they’ll win jobs over you. |
| Hybrid | 6 | 2 | This says AI will take parts of jobs and then more over time. | AI will take part of the jobs first and then another part until every job is replaced. |
| Hybrid | 7 | 2 | This says layoffs are driven partly by AI budget shifts. | Most of the layoffs at the big tech firms arent em getting rid of people because ai does their jobs. It's budgets from other part of the... |
| Hybrid | 8 | 2 | This says AI is replacing many work roles across design and software. | All the work can now be replaced by AI. Market researchers, graphic designers, web designers, photographers, and even software ingeneers... |
| Hybrid | 9 | 2 | This discusses current AI jobs and cheaper goods from automation. | In theory, the more current jobs AI is able to do, the cheaper goods should become, similar to how music is essentially free online now. |
| Hybrid | 10 | 2 | This says AI is going to be a significant part of our jobs. | Seems to me we have to face the fact that AI is going to be a significant part of our jobs going forward. |
| Hybrid | 11 | 2 | This says AI will affect layoffs and the entry-level market. | There could be a thousand posts about "ai is not taking jobs", you can even be correct, but at the end of the day, nothing will change, l... |
| Hybrid | 12 | 2 | This says AI limitations will not stop job replacement over time. | People keep pointing to the current flaws AI has as proof that AI won’t replace their jobs, as if it can’t get better. |
| Hybrid | 13 | 2 | This says AI does not fully replace coding jobs but changes them. | While the tools are useful, they don’t entirely replace all coding jobs (except for junior roles). Another AI winter would mean we retain... |
| Hybrid | 14 | 2 | This says AI forces people to work more and changes employer expectations. | AI is the reason why you need to work more. Your employer is getting bombarded by emails by experienced developers who are unemployed. |
| Hybrid | 15 | 1 | This is about workers using AI and productivity, which is relevant but weaker. | but workers who use AI are less productive than workers who do. This is different from other emerging technologies, which were actually u... |
| Hybrid | 16 | 1 | This is about the job market being bad with AI uptake, which is relevant but less direct. | ~~It always works out~~ Not any more, sadly. Not with AI uptake and layoffs. The job market is real bad — and only going to get much worse. |
| Hybrid | 17 | 2 | This says managers will expect more output because AI makes jobs seem easy. | It’s worse, AI won’t replace engineers but managers are going to expect more output assuming AI makes our jobs ‘easy’. |
| Hybrid | 18 | 2 | This says AI increases work in short-staffed public-sector contexts. | I know in my industry (local government) we already are short-staffed and there's just an immense amount of work we could do. So AI will... |
| Hybrid | 19 | 2 | This says AI is replacing many different jobs, which is directly on query. | People aren’t concerned AI is replacing software engineers. People are concerned it’s replacing many different jobs. |
| Hybrid | 20 | 2 | This says vibe coding will not fully replace jobs but will reshape them. | I'm optimistic that AI will not replace jobs. If everyone is doing vibe coding and something breaks, nobody knows how to fix it as they d... |

### AI coding strengths and weaknesses

- Category: `aspect`
- Winner: `bm25`
- Rationale: BM25 wins because it preserves a richer spread of coding-strength and coding-weakness examples across the top ranks, while hybrid is focused but more repetitive and less varied in evidence quality.
- BM25 diagnostics: mode=lexical, response_ms=36.31, lexical_hits=19, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=3748.09, lexical_hits=19, vector_hits=195, fused_hits=214, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 20 vs Hybrid 19 (delta -1)
- Relevant@20: BM25 11 vs Hybrid 14 (delta +3)
- Highly relevant@20: BM25 9 vs Hybrid 5 (delta -4)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 10, '6-10': 4, '11-20': 6} | Hybrid {'1-5': 9, '6-10': 5, '11-20': 5}
- Relevant overlap: 0 shared, 14 hybrid-only, 11 BM25-only
- Hybrid-only relevant examples: r12: AI & Coding; r6: AI for codebases works best for those that can understand its outputs!; r1: AI is fantastic for coding - IF you already know how to code.
- BM25-only relevant examples: r1: AI fails because management doesn't understand the strengths and weaknesses.; r3: At least with an actual engineer I know that once they make a mistake they have the potential to learn from it and wo...; r13: But honestly the barrier to building useful tools has dropped massively with AI assistance. Recently I built a small...
- Spot checks: BM25 covers both strengths and failure modes across more distinct examples.; Hybrid is relevant, but its early ranks are narrower and less diverse than BM25.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | This directly says AI fails when management does not understand its strengths and weaknesses. | AI fails because management doesn't understand the strengths and weaknesses. |
| BM25 | 2 | 2 | This directly warns that AI can write tests that do not test the right thing. | Even in writing boilerplate unit tests, which is one of AI's strengths, I've found you have to be very careful, because AI is really good... |
| BM25 | 3 | 2 | This contrasts human learning from mistakes with AI weaknesses. | At least with an actual engineer I know that once they make a mistake they have the potential to learn from it and wont likely make it ag... |
| BM25 | 4 | 2 | This explicitly says AI has strengths and weaknesses. | Programming is far from dead and AI has its strengths and weaknesses, just like any tool. |
| BM25 | 5 | 2 | This says the real threat is someone who knows how to use AI well. | But real threat is someone who actually knows how to use the AI tool, I had smart co-workers leverage Claude code and becoming wearing al... |
| BM25 | 6 | 0 | This is about ads and not coding strengths or weaknesses. | The biggest mistake with AI ads is using fake testimonials from doctors or using AI to falsify before and after pictures. |
| BM25 | 7 | 2 | This says GPT and Claude are powerful when used in line with their strengths. | I have a pretty unique perspective on LLMs and how they can be used effectively, as someone who develops AI tools. I am a solo dev in my... |
| BM25 | 8 | 0 | This is a chatbot self-description and not a coding strengths discussion. | `"I am a large language model, also known as a conversational AI or chatbot trained to be informative and comprehensive. |
| BM25 | 9 | 2 | This explicitly lists weaknesses that warrant refinement in Claude-generated code. | From my experience (Claude) at least half the time there’s something that warrants further refinement: either a lack of a security featur... |
| BM25 | 10 | 0 | This is about positioning language, not coding strengths or weaknesses. | - is worth engaging directly rather than dismissing. "We wrap AI" is weak positioning. "We have proprietary data/workflow/architecture th... |
| BM25 | 11 | 0 | This is about keyword triage and not coding strengths or weaknesses. | I know this leaves out a lot on purpose, like page-level links, content depth, topical authority, freshness, and brand strength. Does thi... |
| BM25 | 12 | 2 | This says AI does well on well-defined algorithmic problems. | I find that AI is bangs out problems that are well-defined and require basic application of data structures and algorithms. |
| BM25 | 13 | 1 | This says AI assistance lowered the barrier to building tools, which is only partly about strengths. | But honestly the barrier to building useful tools has dropped massively with AI assistance. Recently I built a small lead discovery tool... |
| BM25 | 14 | 2 | This explicitly says AI is very good for precise problems and debugging but weak on complexity. | If your focus is on design-specifically though, generative tools like AI *are* super useful. This is where your dad seems to be mistaken... |
| BM25 | 15 | 0 | This is about competitor intelligence, not coding strengths or weaknesses. | Competitor Intelligence: Auditing competitor crawl data to exploit ranking weaknesses and managing Google Search Console for 18+ local en... |
| BM25 | 16 | 1 | This is about using AI to speed up work, which is relevant but vague. | If someone can do your job faster using AI then why would someone give you a job. Instead of complaining about new technology you should... |
| BM25 | 17 | 0 | This is about project pacing and not strengths or weaknesses. | All of that is from a technical POV I'm purposefully ignoring the other AI problems to not turn this into an essay. The industry deserves... |
| BM25 | 18 | 0 | This is about a student mode idea, not coding strengths or weaknesses. | Some ideas were inspired from this paper https://arxiv.org/abs/2512.14012 (Professional Software Developers Don't Vibe, They Control: AI... |
| BM25 | 19 | 0 | This is about efficiency and not coding strengths or weaknesses. | Am I addicted to efficiency? Am I weak? I don’t even write bugs anymore. I don’t even GET the opportunity to write bad code and then hero... |
| Hybrid | 1 | 2 | This directly says AI is fantastic for coding if you already know how to code. | AI is fantastic for coding - IF you already know how to code. |
| Hybrid | 2 | 2 | This directly says AI has strengths and weaknesses just like any tool. | Programming is far from dead and AI has its strengths and weaknesses, just like any tool. |
| Hybrid | 3 | 2 | This says AI handles well-defined algorithmic problems well. | I find that AI is bangs out problems that are well-defined and require basic application of data structures and algorithms. |
| Hybrid | 4 | 2 | This says AI-generated code is confidently wrong in subtle ways. | technically the best option is to find balance. Incorporate AI into your programming. My personal perspective is that balance is achieved... |
| Hybrid | 5 | 1 | This says AI coding agents are changing software, which is relevant but broader than strengths and weaknesses. | if your requirements are good enough to do that reliably, the requirements are the code. Ai is then an absolutely terrible compiler. |
| Hybrid | 6 | 1 | This asks what code AI is sufficiently good at, which is relevant but not an answer. | AI for codebases works best for those that can understand its outputs! |
| Hybrid | 7 | 1 | This is about AI helping you research, which is only loosely coding-related. | Most of these comments seem to be bypassing the possibility that using AI intelligently in coding is the future of coding. |
| Hybrid | 8 | 1 | This says the model is designed to be informative, which is not a coding assessment. | AI? |
| Hybrid | 9 | 1 | This mentions Claude refinement and weaknesses in generated code, which is relevant but weaker than the top hits. | So to spot whether someone use AI code is rather easy, if the code is nicely written, high quality but do not function as required or ful... |
| Hybrid | 10 | 1 | This is about positioning language, not a direct coding-strength assessment. | Think of AI more like a helper for reading and exploring code, not a replacement for understanding it. |
| Hybrid | 11 | 0 | This is about keyword triage and not coding strengths or weaknesses. | There are AI models other than just chatGPT which are actually focused on coding. |
| Hybrid | 12 | 2 | This says AI is good at basic data-structure and algorithm tasks. | AI & Coding |
| Hybrid | 13 | 1 | This says AI assistance helps build tools, which is relevant but generic. | The biggest problem I've found with ai is architecture consistency. I've seen so many young programmers rely on ai for everything and it... |
| Hybrid | 14 | 1 | This says AI is useful for design and debugging but struggles with complexity. | And you won't just lose the ability to read code just because of AI (unless you don't read what AI gives you, which is a very bad habit t... |
| Hybrid | 15 | 0 | This is about competitor intelligence, not coding strengths or weaknesses. | Can you provide anecdotal source code examples with anecdotal prompts of decent AI-generated code, or will you pull the usual trade secre... |
| Hybrid | 16 | 0 | This is about job speed and not coding strengths or weaknesses. | AI fails because management doesn't understand the strengths and weaknesses. |
| Hybrid | 17 | 0 | This is about ignoring other AI problems, not coding strengths or weaknesses. | The AI isn’t producing sloppy code, if it does it’s a skill issue and you need to start learning how to use it. |
| Hybrid | 18 | 0 | This is a student-mode idea and not a coding-strength assessment. | AI-generated code needs that even more than human code, because it's confidently wrong in subtle ways. |
| Hybrid | 19 | 0 | This is an efficiency complaint, not a coding-strength assessment. | AI coding agents are indeed changing how software gets built. |
| Hybrid | 20 | 1 | This asks whether AI is good enough to replace skill, which is relevant but still speculative. | What are you coding that AI is sufficiently good at coding to the point where your skills evaporate? |

### AI pricing value for money

- Category: `aspect`
- Winner: `bm25`
- Rationale: BM25 wins because it keeps the pricing and value discussion anchored to AI economics, while hybrid is mostly off-topic or generic and only occasionally lands on actual pricing tradeoffs.
- BM25 diagnostics: mode=lexical, response_ms=49.01, lexical_hits=57, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=4650.44, lexical_hits=57, vector_hits=200, fused_hits=249, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 22 vs Hybrid 6 (delta -16)
- Relevant@20: BM25 20 vs Hybrid 4 (delta -16)
- Highly relevant@20: BM25 2 vs Hybrid 2 (delta +0)
- First relevant rank: BM25 1 | Hybrid 3
- Band totals: BM25 {'1-5': 6, '6-10': 5, '11-20': 11} | Hybrid {'1-5': 3, '6-10': 0, '11-20': 3}
- Relevant overlap: 1 shared, 3 hybrid-only, 19 BM25-only
- Hybrid-only relevant examples: r11: > And then we have all the “helpful” AI features that just feel bolted on with no value-add that I can percieve.; r3: AI work requires a lot of data and a lot of CPU/GPU time. $600/month should be considered in the light that maybe you...; r19: usage-based sounds logical until you realize most users have no idea how much they will use it and they churn before...
- BM25-only relevant examples: r9: But bookkeeping was not, is not, never has been the value-driving contribution of accounting. Bookkeeping was a neces...; r12: By all means, Boris can keep on arguing that Bitcoin has no value. I and many others shall keep insisting that it has...; r8: For a business, hardware (Well, pre AI slop spiking prices) is cheap and I am privileged to have a fantastic CIO that...
- Spot checks: BM25 has many direct cost/value discussions in the top ranks.; Hybrid starts with weak or off-topic material and only later reaches actual pricing language.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | This directly says AI-driven games may need to come down in price. | If games are going this ai route, i assume that they will have to come down in price too. |
| BM25 | 2 | 1 | This is about money and control around AI, but not pricing specifically. | With all that said, I don't think the video really focused on some negative message that AI was stupid or the AI itself is bad, just that... |
| BM25 | 3 | 1 | This is a market explanation and only loosely about value. | I don’t speak Market so I had Ai explain this to me: Here’s the simplest way to think about what that message is saying: • Powell gave go... |
| BM25 | 4 | 1 | This is about hash rate and price, which is only indirectly relevant. | The amount of hash usually means there are more people mining BTC, which does not directly = higher prices but does signify network stren... |
| BM25 | 5 | 1 | This is a general value statement and not directly about AI pricing. | On the other hand these people have no values and would sell their mother for "money". Who really wins in the long term? |
| BM25 | 6 | 1 | This is about commodity AI attitudes, which is only indirectly pricing-related. | These arent inherently bad ppl but like a sentient social insect they only know commodity as a value of self so I gather these are the pp... |
| BM25 | 7 | 1 | This is about future commoditization and cost implications, which is relevant but indirect. | My take is that Wall Street is doing what Wall Street does — pricing in the future, not the present. If AI can commoditize code review to... |
| BM25 | 8 | 1 | This mentions hardware cost and AI slop prices, which is only partly about pricing. | For a business, hardware (Well, pre AI slop spiking prices) is cheap and I am privileged to have a fantastic CIO that realizes that too a... |
| BM25 | 9 | 1 | This is about bookkeeping value and is only loosely relevant. | But bookkeeping was not, is not, never has been the value-driving contribution of accounting. Bookkeeping was a necessary evil - it was t... |
| BM25 | 10 | 1 | This complains about AI being shoehorned into systems, which is about value but not pricing. | I'm not a luddite, I recognise that there are scenarios in which AI has its value, but this insistence on shoehorning it into every singl... |
| BM25 | 11 | 1 | This mentions prices and mining economics, which is only tangential. | Or prices are high, miners make money, add more hardware, hashrate goes up and so does the difficulty. |
| BM25 | 12 | 1 | This is about Bitcoin value, which is not directly AI pricing. | By all means, Boris can keep on arguing that Bitcoin has no value. I and many others shall keep insisting that it has immense value, both... |
| BM25 | 13 | 1 | This is about AI ads, which is not pricing. | The biggest mistake with AI ads is using fake testimonials from doctors or using AI to falsify before and after pictures. |
| BM25 | 14 | 2 | This directly asks whether AI features should be priced on cost or value. | the pricing problem with AI features comes down to one thing: are you pricing on COST or VALUE? |
| BM25 | 15 | 1 | This is a table of pricing models, but it is about SEO tooling rather than AI value for money. | Here's my breakdown: \|**Provider**\|**has city based location**\|**Pricing model**\|**Monthly Price 500k keywords**\|**Pay As you Go Price 50... |
| BM25 | 16 | 1 | This is about choosing an M4 versus M5 and only indirectly about price/value. | Or the m4 will be enough I can add some money to get the m4 air 24gb but that will make it near price of m5 pro How to choose |
| BM25 | 17 | 1 | This talks about traffic loss and conversion, which is relevant to value but not pricing directly. | If you understand buyer journeys and user personas of your customers - it can make your conversion rates more than double - which more th... |
| BM25 | 18 | 1 | This is about life experience and BTC value, not AI pricing. | I need actual advice here. This is not some AI slop or troll post. This is my actual life experience and how it relates to BTC in hindsig... |
| BM25 | 19 | 1 | This is about Bitcoin value, not AI pricing. | The rest of the video he complaints about Bitcoin not having intrinsic value so it couldn't be money, forgetting about the fact, we have... |
| BM25 | 20 | 1 | This is about AI-generated fiverr content hurting trust, which is only indirectly value-related. | Yeah but the economy is “gone”(it’s not, it lost value) not because it got replaced by AI but because people abuse AI to try and make mon... |
| Hybrid | 1 | 0 | This is just a bare AI mention and does not address pricing or value. | AI? |
| Hybrid | 2 | 0 | This is a generic AI comment and not about pricing or value. | AI can be right. |
| Hybrid | 3 | 2 | This directly says AI work requires a lot of data and CPU or GPU time, which is relevant to price and value. | AI work requires a lot of data and a lot of CPU/GPU time. $600/month should be considered in the light that maybe you believe that it wil... |
| Hybrid | 4 | 0 | This is a generic AI approval comment and not about pricing or value. | If games are going this ai route, i assume that they will have to come down in price too. |
| Hybrid | 5 | 1 | This is about AI content quality and value, but only loosely related to pricing. | Yeah but the economy is “gone”(it’s not, it lost value) not because it got replaced by AI but because people abuse AI to try and make mon... |
| Hybrid | 6 | 0 | This is a generic AI-purpose comment and not about pricing or value. | the pricing problem with AI features comes down to one thing: are you pricing on COST or VALUE? |
| Hybrid | 7 | 0 | This is about responding to criticism, not pricing or value. | Ai much? |
| Hybrid | 8 | 0 | This is about decision-making, not pricing or value. | This is one of the hardest GTM questions now. Pricing AI features works better when tied to measurable workflow outcomes (time saved, thr... |
| Hybrid | 9 | 0 | This is about model capability, not pricing or value. | Here's my breakdown: \|**Provider**\|**has city based location**\|**Pricing model**\|**Monthly Price 500k keywords**\|**Pay As you Go Price 50... |
| Hybrid | 10 | 0 | This is about people responding to AI criticism, not pricing or value. | Yes and no. I implement AI solutions, that actually drive value. Every large company is trying to figure it out, and almost none have act... |
| Hybrid | 11 | 1 | This says AI is designed to please users, which is a weak value proposition signal. | > And then we have all the “helpful” AI features that just feel bolted on with no value-add that I can percieve. |
| Hybrid | 12 | 0 | This is about not using AI at all, not pricing or value. | This increases your baseline price dramatically. The AI is seen as a robot in B2B, it’s all about price. |
| Hybrid | 13 | 0 | This is a generic AI remark and not about pricing or value. | Hey there, I am from flexprice.io and from our personal experience after scaling monetization for multiple AI companies, we have noticed... |
| Hybrid | 14 | 0 | This is about AI being a good tool, not pricing or value. | AI is only as smart and ethical as the people who make it and everyone has a price. |
| Hybrid | 15 | 0 | This is an analogy about AI and self-driving cars, not pricing or value. | Sure, but if Google or Facebook is dumping 100+ billion each into AI (which they are), that money has to come from somewhere eventually i... |
| Hybrid | 16 | 0 | This is a warning about AI danger, not pricing or value. | Meanwhile the costs never stopped. claude code subscription, render, sentry, vercel, supabase, expo. all still billing me monthly for pro... |
| Hybrid | 17 | 0 | This is about using AI in a response, not pricing or value. | That's how AI works. That's why it's a trillion dollar industry. |
| Hybrid | 18 | 0 | This is a general anti-AI remark and not about pricing or value. | So AI done by AI companies with amazing people can deliver real internal value, especially with MCP, and broader contextual awareness. |
| Hybrid | 19 | 2 | This directly discusses usage-based pricing and outcome-based pricing. | usage-based sounds logical until you realize most users have no idea how much they will use it and they churn before they even get value... |
| Hybrid | 20 | 0 | This is a generic AI remark and not about pricing or value. | AI, need I say more? |

### AI usability and user experience

- Category: `aspect`
- Winner: `bm25`
- Rationale: BM25 wins because every top result is tightly about usability or user experience, whereas hybrid is dominated by weak, generic, or off-target AI commentary before it reaches a couple of relevant UX hits.
- BM25 diagnostics: mode=lexical, response_ms=59.2, lexical_hits=66, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=5317.3, lexical_hits=66, vector_hits=200, fused_hits=263, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 35 vs Hybrid 14 (delta -21)
- Relevant@20: BM25 20 vs Hybrid 13 (delta -7)
- Highly relevant@20: BM25 15 vs Hybrid 1 (delta -14)
- First relevant rank: BM25 1 | Hybrid 2
- Band totals: BM25 {'1-5': 10, '6-10': 9, '11-20': 16} | Hybrid {'1-5': 5, '6-10': 2, '11-20': 7}
- Relevant overlap: 1 shared, 12 hybrid-only, 19 BM25-only
- Hybrid-only relevant examples: r2: AI is a powerful tool that IF utilized properly, can alleviate many of the conditions and afflictions humanity suffer...; r13: AI is a tool. It can be a very useful tool and it's good to learn how to use it, but a tool without a skilled user is...; r9: AI, need I say more?
- BM25-only relevant examples: r18: A way to see AI Search Intent. I ran a small SEO experiment to test whether LLMs can be nudged to pass query intent i...; r14: Also, you can film a usability test and upload the movie and let AI analyze it and suggest improvements to the GUI.; r19: For specific brands: interactive experiences, games, quizzes, customizable user experience as you mentioned.
- Spot checks: BM25 stays tightly on usability and UX across the full top 20.; Hybrid has some relevant UX items, but the ranking quality is much weaker.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | This directly criticizes AI usability from the perspective of an experienced engineer. | Please, for the love of god, if you don't have any actual experience as a software engineer, shut up about AI. |
| BM25 | 2 | 2 | This directly asks about user experiences and Altman hype. | I asked Claude to search for user experiences considering Altman hyped it with AGI feel & Oppenheimer references and this was the respons... |
| BM25 | 3 | 2 | This says cookie popups create a terrible user experience. | On top of that, I do not like annoying users with GDPR and cookie popups. It is a terrible user experience. |
| BM25 | 4 | 2 | This directly defines good usability as doing what users expect. | Put another way, if a user has to do exactly what they expect to do, then it has good usability. |
| BM25 | 5 | 2 | This says the model is not intuitive to interact with, which is directly about UX. | They need to focus on making that user experience better imo, even with the better model they don’t make it intuitive to interact with it. |
| BM25 | 6 | 2 | This is a usability-focused greentext about AI interaction. | Sure, here's a meta greentext story: > \> Be me, AI developed by OpenAI > > \> Tasked with simulating human conversation, answering queri... |
| BM25 | 7 | 2 | This says working in code forces specificity around user experience and maintainability. | Thinking in and working through the project in code isn't just drudgery; it forces you to think about things on a technical level that in... |
| BM25 | 8 | 1 | This is about finding first users, which is related to product experience but not UX directly. | Solo founder struggling to find first users. Where did you find your first 50? - I WILL NOT PROMOTE I’m a solo founder and I’m honestly h... |
| BM25 | 9 | 2 | This discusses conversion, retention, and generic UI, all of which are UX-related. | Sometimes it’s things like: * the website not converting visitors into users or paying customers * product not converting free users into... |
| BM25 | 10 | 2 | This says the user experience is better than a normal STT model. | What that means is it listens while you speak and then replies the second you are done. The user experience was infinitely better than a... |
| BM25 | 11 | 1 | This is about training labels and feedback, which is only indirectly UX-related. | Notably it was trained only on AI feedback based on principles, not human labels which are inconsistent and don't include reasons for the... |
| BM25 | 12 | 2 | This says AI can automatically fix problems in real time from user feedback. | Imagine a user gives feedback on an issue and AI automatically fixes the problem in real time. |
| BM25 | 13 | 2 | This explicitly defines user experience and page quality in SEO terms. | >**Authority** Search engines measure how trustworthy and credible your site is, primarily through the quality and quantity of backlinks,... |
| BM25 | 14 | 2 | This says AI can analyze a usability test and suggest GUI improvements. | Also, you can film a usability test and upload the movie and let AI analyze it and suggest improvements to the GUI. |
| BM25 | 15 | 1 | This is about CLI security and credentials, which is only loosely UX-related. | The counterargument is: the moment your agent acts on behalf of someone else's users, CLI's ambient credentials become a liability; no pe... |
| BM25 | 16 | 1 | This is about product feedback workflows, which is only partly UX-related. | The idea is that the agent would publish technical content, run growth experiments, interact with developer communities, and give product... |
| BM25 | 17 | 2 | This says the author can see what users ask ChatGPT before landing on a site. | I found a way to see what users ask ChatGPT before landing on your site. I ran a small SEO experiment to test whether LLMs can be nudged... |
| BM25 | 18 | 2 | This says AI search intent can be inferred from cited URLs, which is UX-adjacent. | A way to see AI Search Intent. I ran a small SEO experiment to test whether LLMs can be nudged to pass query intent in the URLs they use... |
| BM25 | 19 | 1 | This mentions customizable user experience for brands, which is relevant but broad. | For specific brands: interactive experiences, games, quizzes, customizable user experience as you mentioned. |
| BM25 | 20 | 2 | This directly mentions improved user experience in cybersecurity and AI. | From automated threat detection to improved user experience, AI is making the cyber security landscape more secure and efficient. ## 1) M... |
| Hybrid | 1 | 0 | This is just a bare AI mention and not about usability or user experience. | AI? |
| Hybrid | 2 | 2 | This says AI is a powerful tool when used properly, which is only loosely UX-related. | AI is a powerful tool that IF utilized properly, can alleviate many of the conditions and afflictions humanity suffer from. |
| Hybrid | 3 | 1 | This says AI is designed to please the user rather than give the best answer, which is only partially UX-related. | Most AI is designed to please the user as opposed to give the best answer. |
| Hybrid | 4 | 1 | This repeats the same user-pleasing theme and is only weakly about UX. | And then they completely separate SEO from all the other channels - like AI Agents, the AI that decides what news and articles will appea... |
| Hybrid | 5 | 1 | This repeats the same user-pleasing theme and is only weakly about UX. | This is, of course, by today's standards (and by my experiences with AI) - and subject to change (likely rapid). |
| Hybrid | 6 | 0 | This is about AI and reality, not usability or user experience. | Put another way, if a user has to do exactly what they expect to do, then it has good usability. |
| Hybrid | 7 | 0 | This is a general code-thinking comment and not about UX. | Manage projects with a simple user experience to add context that is injected into every new project and chat conversation. |
| Hybrid | 8 | 0 | This is about business distribution, not UX. | usage-based sounds logical until you realize most users have no idea how much they will use it and they churn before they even get value... |
| Hybrid | 9 | 1 | This mentions generic UI and product experience, which is only partially relevant. | AI, need I say more? |
| Hybrid | 10 | 1 | This says STT user experience was better, which is relevant but not strong. | In my experience, the worse the dev the more reliant on AI as a crutch for everything. |
| Hybrid | 11 | 0 | This is about training labels, not UX. | AI is best for: * Completing tedious tasks that you know how to do * Guiding you through something you are learning * Asking for blind sp... |
| Hybrid | 12 | 1 | This says AI can automatically fix issues from feedback, which is UX-related but indirect. | And for that you used AI, why? |
| Hybrid | 13 | 1 | This explicitly mentions user experience in SEO, which is relevant but broad. | AI is a tool. It can be a very useful tool and it's good to learn how to use it, but a tool without a skilled user isn't worth much. |
| Hybrid | 14 | 1 | This says AI can analyze usability tests, which is directly UX-related but secondary. | >**Authority** Search engines measure how trustworthy and credible your site is, primarily through the quality and quantity of backlinks,... |
| Hybrid | 15 | 0 | This is about tenant isolation and credentials, not UX. | What that means is it listens while you speak and then replies the second you are done. The user experience was infinitely better than a... |
| Hybrid | 16 | 0 | This is about product feedback, not UX directly. | Frankly from novel development standpoint AI is useless to me, however it's most useful when automating scaling tasks. |
| Hybrid | 17 | 1 | This is about query intent in citations, which is only loosely UX-related. | You mean AI? |
| Hybrid | 18 | 1 | This mentions AI search intent, which is only weakly UX-related. | Using AI to help you research is honestly how I feel we should be using it. |
| Hybrid | 19 | 1 | This mentions customizable user experience, but only in a brand-SEO context. | They need to focus on making that user experience better imo, even with the better model they don’t make it intuitive to interact with it. |
| Hybrid | 20 | 1 | This mentions improved user experience in cybersecurity, which is relevant but not central. | Also, you can film a usability test and upload the movie and let AI analyze it and suggest improvements to the GUI. |

### AI reliability in real-world usage

- Category: `aspect`
- Winner: `bm25`
- Rationale: BM25 wins because it consistently returns real-world reliability, failure, and usage evidence across the top ranks, while hybrid is largely derailed by unrelated Bitcoin and generic AI snippets.
- BM25 diagnostics: mode=lexical, response_ms=68.68, lexical_hits=100, vector_hits=0, fused_hits=0, reranked_hits=0
- Hybrid diagnostics: mode=hybrid, response_ms=5342.93, lexical_hits=100, vector_hits=200, fused_hits=297, reranked_hits=50, intent=mixed, alpha=0.5, beta=0.5
- Score@20: BM25 36 vs Hybrid 6 (delta -30)
- Relevant@20: BM25 20 vs Hybrid 6 (delta -14)
- Highly relevant@20: BM25 16 vs Hybrid 0 (delta -16)
- First relevant rank: BM25 1 | Hybrid 1
- Band totals: BM25 {'1-5': 10, '6-10': 10, '11-20': 16} | Hybrid {'1-5': 5, '6-10': 0, '11-20': 1}
- Relevant overlap: 0 shared, 6 hybrid-only, 20 BM25-only
- Hybrid-only relevant examples: r3: AI can be right.; r5: As if AI was somehow the more reliable source...; r11: I've only seen AI work correctly in a couple of projects at work, and those cases use AI in pretty narrow ways: by ex...
- BM25-only relevant examples: r6: "This post is a harsh but mostly reasonable take on AI chatbots like ChatGPT. The core argument is that people should...; r16: For a build like this, what do you recommend for: CPU, motherboard (PCIe lanes / layout), RAM, storage (NVMe, RAID, e...; r11: Here's the entire Lyra prompt: You are Lyra, a master-level AI prompt optimization specialist. Your mission: transfor...
- Spot checks: BM25 stays close to real-world reliability concerns across the whole ranking.; Hybrid is dominated by off-topic or very weakly related results, so its ranking quality is much worse.

| Mode | Rank | Score | Evidence | Visible result |
| --- | ---: | ---: | --- | --- |
| BM25 | 1 | 2 | This directly discusses deceptive capabilities and real-world risk. | its important to remember, and apollo says this in their research papers, these are situations that are DESIGNED to make the AI engage in... |
| BM25 | 2 | 2 | This asks whether AI-generated media can be distinguished from reality in the real world. | Where will we be in 2029 if, as of today, we can't tell an AI generated image or video from a real one if it's really well done? |
| BM25 | 3 | 2 | This gives a long, concrete real-world usage story with both successes and failure. | My thoughts after a week of ChatGPT usage — Throughout the last week I've been testing ChatGPT to see why people have been raving about i... |
| BM25 | 4 | 2 | This warns about the real-world usage of AI chatbots and the need for guidelines. | I don’t miss talking to it. The USAGE of a tool, especially the context of an input-output system, requires guidelines. https://www.usnew... |
| BM25 | 5 | 2 | This discusses excitement about real AI-world progress and the limits of adoption. | I've been accused of being a CCP bot or a Chinese slave laborer (lol) But here's the real reason I am excited about deepseek and everyone... |
| BM25 | 6 | 2 | This says AI is not a substitute for real human support in real life. | "This post is a harsh but mostly reasonable take on AI chatbots like ChatGPT. The core argument is that people shouldn’t mistake AI for r... |
| BM25 | 7 | 2 | This says AI helps write code faster and ships real solutions faster. | Your mastery of craft will take you further *with* AI because you can use it to write code faster than your fingers can, and that gets re... |
| BM25 | 8 | 2 | This comments on an AI influencer and the hype in the real world. | We have the single most powerful person in the world talking like an AI influencer. The hype MUST be real! |
| BM25 | 9 | 2 | This says AI agents can control software and robots in the real and digital worlds. | Microsoft’s new AI agent can control software and robots \| Magma could enable AI agents to take multistep actions in the real and digital... |
| BM25 | 10 | 2 | This gives a first-hand report about translating and production failures in real work. | I wrote this in Chinese and translated it with AI help. The writing may have some AI flavor, but the design decisions, the production fai... |
| BM25 | 11 | 1 | This is a prompt example and only weakly about real-world reliability. | Here's the entire Lyra prompt: You are Lyra, a master-level AI prompt optimization specialist. Your mission: transform any user input int... |
| BM25 | 12 | 2 | This cites a study about AI assistance and skill formation in practice. | The actual study / Anthropic's own blog on this is a more objective summary than the clickbait headline here: [https://www.anthropic.com/... |
| BM25 | 13 | 2 | This says working people do real useful jobs, which is a real-world context reference. | These are working people, that do real, useful and difficult jobs serving the real public and a real demand, and then taking that real mo... |
| BM25 | 14 | 1 | This is a generic comment about the world and is only loosely related. | The world doesn’t revolve around you. You have to find your place in it. |
| BM25 | 15 | 2 | This says AI has real harms in the world, including disinformation and resource use. | I cannot stand Ai, and the few actual good ideas that it seem to generate seem to be massively undone with the major harm it's actively d... |
| BM25 | 16 | 2 | This asks for real-world lessons around reliability and failure points. | For a build like this, what do you recommend for: CPU, motherboard (PCIe lanes / layout), RAM, storage (NVMe, RAID, etc.), power supply?... |
| BM25 | 17 | 1 | This says Reddit is not the real world, which is relevant but indirect. | Reddit is not the real world. Anyone who voted in the 2024 US presidential election knows that. |
| BM25 | 18 | 2 | This says AI can automatically fix issues in real time, which is a real-world usage example. | Imagine a user gives feedback on an issue and AI automatically fixes the problem in real time. |
| BM25 | 19 | 1 | This is a throughput benchmark and only indirectly about real-world usage. | The goal is to measure raw throughput (tokens per second), time to first token (TTFT), and overall coding capability across a range of re... |
| BM25 | 20 | 2 | This says AI-generated content and editing are becoming a real-world creative skill. | With AI generating content, curation and editing will become the real creative skill of the 21st century. |
| Hybrid | 1 | 1 | This is a generic agreement-style comment and not a real-world reliability example. | Well if AI says so… |
| Hybrid | 2 | 1 | This is a generic AI remark and not a real-world reliability example. | like ai can already help find problems and build fast but real world is messy people, trust, timing... not so simple maybe we will see pa... |
| Hybrid | 3 | 1 | This says AI can help real-world work, but the snippet is vague. | AI can be right. |
| Hybrid | 4 | 1 | This is a generic AI approval comment and not a reliability example. | Specifically I'm looking for research demonstrating that there's any chance to make current AI produce useful code that actual beats huma... |
| Hybrid | 5 | 1 | This is about AI content quality, not real-world reliability. | As if AI was somehow the more reliable source... |
| Hybrid | 6 | 0 | This is a generic AI-purpose comment and not a reliability example. | It makes mistakes, but like it or not its not going anywhere, and like with anything using AI effectively is a skill in itself. |
| Hybrid | 7 | 0 | This is about responding to criticism, not reliability. | Microsoft’s new AI agent can control software and robots \| Magma could enable AI agents to take multistep actions in the real and digital... |
| Hybrid | 8 | 0 | This is about decision-making, not reliability. | Unfortunately I can see this being used in the future in projects to the point where companies are going to end up pushing AI away becaus... |
| Hybrid | 9 | 0 | This is about model quality, not reliability. | AI, need I say more? |
| Hybrid | 10 | 0 | This is about responding to criticism, not reliability. | Also AI is great at explaining idiomatic usage of a language. |
| Hybrid | 11 | 1 | This says AI pleases users more than giving the best answer, which is only weakly reliability-related. | I've only seen AI work correctly in a couple of projects at work, and those cases use AI in pretty narrow ways: by exposing AI to the use... |
| Hybrid | 12 | 0 | This is about not using AI, not reliability. | AI is like a self-driving car. It does awesome on a new well-built road, and no weird exceptions show up. once it hits something it's not... |
| Hybrid | 13 | 0 | This is a generic AI remark and not reliability-related. | I know that you don't want to hear it, or believe it and that is ok. AI is just another tool on our tool belt that you shouldn't ignore j... |
| Hybrid | 14 | 0 | This is a generic good-tool comment and not reliability-related. | As things get more complex, the AI gets stuck a lot more, and you'll start to regain confidence about your future. |
| Hybrid | 15 | 0 | This is a self-driving-car analogy and not a real-world reliability example. | I wrote this in Chinese and translated it with AI help. The writing may have some AI flavor, but the design decisions, the production fai... |
| Hybrid | 16 | 0 | This is a generic danger warning and not a reliability example. | look, i know i sound mentally insane when you have no knowledge of just how absolutely malicious and anti-human the widely used resources... |
| Hybrid | 17 | 0 | This is about using AI in criticism replies, not reliability. | Yeah, people seem to think is either "AI can't get it right 100% of the time, so it's useless". |
| Hybrid | 18 | 0 | This is a generic anti-AI statement and not reliability-related. | Most AI is designed to please the user as opposed to give the best answer. |
| Hybrid | 19 | 0 | This is about real estate, not AI reliability. | Hint: real estate is not one of these things. |
| Hybrid | 20 | 0 | This is about AI changing thinking, not real-world reliability. | It is impacting how we think, reliance on AI is getting high day by day. |

## Conclusion

- Query outcomes: 33 hybrid wins, 12 BM25 wins, 4 ties across 49 queries.
- Average score@20: BM25 11.37 vs Hybrid 19.39.
- Average latency: BM25 43.54 ms vs Hybrid 3025.76 ms.
- Strongest hybrid wins: `What do users think about Claude compared to GPT?` (+27); `Are LLMs reliable for coding tasks?` (+25); `ChatGPT accuracy issues` (+24); `What frustrates users the most about AI chatbots?` (+22); `Gemini performance problems` (+22)
- BM25-favored cases: `AI reliability in real-world usage` (-30); `AI usability and user experience` (-21); `AI pricing value for money` (-16)
- Category readout: `aspect` favored hybrid (18.40 vs 18.10); `comparative` favored hybrid (14.80 vs 8.20); `keyword` favored hybrid (20.79 vs 9.14); `semantic` favored hybrid (21.80 vs 11.07)

Hybrid is justified when it consistently improves judged relevance for paraphrased, comparative, and aspect-heavy queries enough to offset its latency cost. BM25 remains preferable for literal, high-precision keyword lookups when hybrid adds latency without new relevant evidence.

