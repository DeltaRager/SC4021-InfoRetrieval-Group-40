"""Generate PDF document explaining Lemmatization and Concept Extraction."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted,
    PageBreak, KeepTogether,
)

OUTPUT = "/home/user/4021/NLP_Implementation_Guide.pdf"

styles = getSampleStyleSheet()

# Custom styles
styles.add(ParagraphStyle(
    "DocTitle", parent=styles["Title"], fontSize=18, spaceAfter=4,
))
styles.add(ParagraphStyle(
    "DocSubtitle", parent=styles["Normal"], fontSize=12, alignment=TA_CENTER,
    spaceAfter=16, textColor=HexColor("#555555"),
))
styles.add(ParagraphStyle(
    "SectionHead", parent=styles["Heading1"], fontSize=14, spaceAfter=6,
    spaceBefore=16, backColor=HexColor("#e8f5e9"), borderPadding=4,
    textColor=HexColor("#2e7d32"),
))
styles.add(ParagraphStyle(
    "SubHead", parent=styles["Heading2"], fontSize=12, spaceAfter=4,
    spaceBefore=10,
))
styles.add(ParagraphStyle(
    "SubSubHead", parent=styles["Heading3"], fontSize=10.5, spaceAfter=3,
    spaceBefore=8, fontName="Helvetica-BoldOblique",
))
styles.add(ParagraphStyle(
    "Body", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6,
))
styles.add(ParagraphStyle(
    "MyBullet", parent=styles["Normal"], fontSize=10, leading=14,
    leftIndent=16, bulletIndent=6, spaceAfter=3,
))
styles.add(ParagraphStyle(
    "MyCode", parent=styles["Code"], fontSize=8.5, leading=12,
    backColor=HexColor("#f5f5f5"), borderPadding=6, spaceAfter=8,
    fontName="Courier",
))
styles.add(ParagraphStyle(
    "SmallItalic", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Oblique",
    textColor=HexColor("#666666"), spaceAfter=6,
))
styles.add(ParagraphStyle(
    "Ref", parent=styles["Normal"], fontSize=9, leading=12, spaceAfter=2,
))


def make_table(headers, rows, col_widths=None):
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e8f5e9")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


story = []

# ====== TITLE ======
story.append(Paragraph("Lemmatization &amp; Concept Extraction", styles["DocTitle"]))
story.append(Paragraph(
    "Implementation Principles for the Indexing &amp; Searching Module",
    styles["DocSubtitle"],
))
story.append(Spacer(1, 6))

# ====== 1. OVERVIEW ======
story.append(Paragraph("1. Overview", styles["SectionHead"]))
story.append(Paragraph(
    "Our search system is built on Apache Solr with the eDisMax query parser. "
    "To enhance search quality beyond Solr's default keyword matching, we implemented "
    "two NLP techniques at both index time and query time:",
    styles["Body"],
))
story.append(Paragraph(
    "<b>Lemmatization</b> &mdash; normalises words to their dictionary forms so that "
    "morphological variants (e.g. 'running' vs 'run', 'forgotten' vs 'forget') can match each other.",
    styles["MyBullet"], bulletText="\u2022",
))
story.append(Paragraph(
    "<b>Concept Extraction</b> &mdash; identifies meaningful multi-word phrases and named entities "
    "from text, enabling semantic-level matching and intelligent stopword handling.",
    styles["MyBullet"], bulletText="\u2022",
))
story.append(Paragraph(
    "Both techniques are implemented in a shared Python module (<font name='Courier'>nlp_utils.py</font>) "
    "using <b>spaCy</b> (<font name='Courier'>en_core_web_sm</font>) for lemmatization, POS tagging, "
    "noun chunk extraction, and NER, combined with <b>YAKE</b> for unsupervised keyphrase extraction. "
    "The same pipeline runs at index time (to enrich documents) and at query time (to enhance user queries).",
    styles["Body"],
))

# ====== 2. LEMMATIZATION ======
story.append(Paragraph("2. Lemmatization", styles["SectionHead"]))

story.append(Paragraph("2.1 What is Lemmatization?", styles["SubHead"]))
story.append(Paragraph(
    "Lemmatization reduces inflected or derived words to their base dictionary form (lemma). "
    "Unlike stemming (which blindly chops suffixes), lemmatization uses Part-of-Speech (POS) "
    "tagging to determine the correct base form. For example, the Porter stemmer cannot "
    "reduce 'forgotten' to 'forget' (it stays as 'forgotten'), but spaCy's lemmatizer "
    "correctly identifies it as a past participle (VERB) and returns 'forget'.",
    styles["Body"],
))

story.append(Paragraph("2.2 How spaCy Lemmatization Works", styles["SubHead"]))
story.append(Paragraph(
    "The spaCy pipeline processes text through three stages in a single pass:",
    styles["Body"],
))
story.append(Paragraph(
    "<b>Step 1 &mdash; Tokenization:</b> The tokenizer splits the text into individual tokens "
    "(words, punctuation).",
    styles["MyBullet"], bulletText="\u2022",
))
story.append(Paragraph(
    "<b>Step 2 &mdash; POS Tagging:</b> A statistical model assigns a Part-of-Speech tag to each "
    "token (VERB, NOUN, ADJ, ADV, etc.) based on the surrounding context.",
    styles["MyBullet"], bulletText="\u2022",
))
story.append(Paragraph(
    "<b>Step 3 &mdash; Lemmatization:</b> The lemmatizer looks up the correct dictionary form based "
    "on both the token text AND its POS tag. It uses a rule-based lookup table combined with an "
    "exception dictionary for irregular forms (e.g. 'bought' &rarr; 'buy', 'better' &rarr; 'good').",
    styles["MyBullet"], bulletText="\u2022",
))

story.append(Paragraph("2.3 Implementation Code", styles["SubHead"]))
story.append(Preformatted(
    'def lemmatize_text(text: str) -> str:\n'
    '    nlp = spacy.load("en_core_web_sm")\n'
    '    doc = nlp(text)     # runs tokenizer + POS tagger + lemmatizer\n'
    '    tokens = [\n'
    '        token.lemma_.lower()\n'
    '        for token in doc\n'
    '        if not token.is_punct and token.text.strip()\n'
    '    ]\n'
    '    return " ".join(tokens)',
    styles["MyCode"],
))

story.append(Paragraph("2.4 Lemmatization Examples", styles["SubHead"]))
story.append(make_table(
    ["Input Token", "POS Tag", "Lemma", "Explanation"],
    [
        ["running", "VERB", "run", "Regular verb: remove -ing suffix"],
        ["bought", "VERB", "buy", "Irregular verb: exception dictionary lookup"],
        ["forgotten", "VERB", "forget", "Irregular past participle: dictionary lookup"],
        ["dogs", "NOUN", "dog", "Regular noun: remove plural -s"],
        ["better", "ADJ", "good", "Irregular comparative: dictionary lookup"],
        ["artificially", "ADV", "artificially", "Adverb: already base form (no change)"],
        ["intelligence", "NOUN", "intelligence", "Noun: already base form (no change)"],
    ],
    col_widths=[70, 50, 65, 300],
))
story.append(Spacer(1, 6))

story.append(Paragraph("2.5 Why Lemmatization Alone Is Not Enough", styles["SubHead"]))
story.append(Paragraph(
    "Lemmatization only reduces words to their own POS's base form. It does NOT convert "
    "across parts of speech. For example, 'artificially' (ADV) stays as 'artificially' &mdash; "
    "it is NOT reduced to 'artificial' (ADJ). Similarly, 'intelligent' (ADJ) stays as "
    "'intelligent' &mdash; it is NOT reduced to 'intelligence' (NOUN).",
    styles["Body"],
))
story.append(Paragraph(
    "This is why we combine lemmatization with Solr's built-in Porter stemmer. The Porter "
    "stemmer aggressively truncates suffixes without regard to POS:",
    styles["Body"],
))
story.append(make_table(
    ["Word", "Lemma (spaCy)", "Stem (Porter)", "Result"],
    [
        ["artificial", "artificial", "artifici", "Same stem family"],
        ["artificially", "artificially", "artifici", "Same stem family"],
        ["intelligence", "intelligence", "intellig", "Same stem family"],
        ["intelligent", "intelligent", "intellig", "Same stem family"],
        ["forgotten", "forget", "forgotten*", "Lemma fixes what stem cannot"],
        ["bought", "buy", "bought*", "Lemma fixes what stem cannot"],
    ],
    col_widths=[80, 80, 80, 245],
))
story.append(Paragraph(
    "* Porter stemmer cannot handle irregular forms; lemmatization fills this gap.",
    styles["SmallItalic"],
))

story.append(Paragraph("2.6 Dual-Layer Architecture in Our System", styles["SubHead"]))
story.append(Paragraph(
    "At index time, each document gets two versions of its text stored in Solr:",
    styles["Body"],
))
story.append(Paragraph(
    "<b>full_text</b> (original text) &mdash; indexed with Solr's <font name='Courier'>text_en</font> "
    "field type, which applies Porter stemming automatically.",
    styles["MyBullet"], bulletText="\u2022",
))
story.append(Paragraph(
    "<b>lemmatized_text</b> (spaCy lemmatized text) &mdash; also indexed as "
    "<font name='Courier'>text_en</font>, so Porter stemming is applied ON TOP of lemmatization.",
    styles["MyBullet"], bulletText="\u2022",
))
story.append(Paragraph("At query time, the search process works as follows:", styles["Body"]))
story.append(Preformatted(
    'User query: "artificially intelligent"\n'
    '  |-- Primary search (q) on full_text / title / body / lemmatized_text / concepts\n'
    '  |     Solr applies Porter stem: "artificially" -> "artifici"\n'
    '  |     Matches documents containing "artificial" (same stem: "artifici")\n'
    '  |\n'
    '  |-- Boost query (bq) on lemmatized_text with lemmatized query\n'
    '        spaCy lemma: "artificially intelligent" (unchanged for ADV+ADJ)\n'
    '        Solr stems: "artificially" -> "artifici", "intelligent" -> "intellig"\n'
    '        Documents whose lemmatized_text matches get EXTRA ranking score\n'
    '\n'
    'User query: "forgotten passwords"\n'
    '  |-- Primary search: Porter stem "forgotten" -> "forgotten" (CANNOT match "forget")\n'
    '  |-- Boost query: spaCy lemma "forget password"\n'
    '        Porter stem: "forget" -> "forget" -- NOW matches documents with "forget"!\n'
    '        This is where lemmatization adds value that stemming alone cannot.',
    styles["MyCode"],
))

# ====== 3. CONCEPT EXTRACTION ======
story.append(PageBreak())
story.append(Paragraph("3. Concept Extraction", styles["SectionHead"]))

story.append(Paragraph("3.1 What is Concept Extraction?", styles["SubHead"]))
story.append(Paragraph(
    "Concept Extraction identifies meaningful multi-word expressions, keyphrases, and named "
    "entities from text. In our system it serves two purposes: (1) enabling semantic-level "
    "matching where individual keywords would fail, and (2) providing intelligent stopword "
    "removal that preserves stopwords inside meaningful phrases.",
    styles["Body"],
))

story.append(Paragraph("3.2 Three Complementary Techniques", styles["SubHead"]))

story.append(Paragraph("3.2.1 spaCy Noun Chunk Extraction (Syntactic Parsing)", styles["SubSubHead"]))
story.append(Paragraph(
    "spaCy's dependency parser analyses the grammatical structure of each sentence and "
    "groups tokens into noun chunks (noun phrases). A noun chunk is a contiguous span "
    "centred on a head noun together with its dependents (determiners, adjectives, "
    "prepositional modifiers).",
    styles["Body"],
))
story.append(Paragraph("Processing steps:", styles["Body"]))
story.append(Paragraph("<b>1.</b> The tokenizer splits text into tokens.", styles["MyBullet"], bulletText=" "))
story.append(Paragraph("<b>2.</b> The POS tagger assigns part-of-speech tags (NOUN, DET, ADP, ADJ, ...).", styles["MyBullet"], bulletText=" "))
story.append(Paragraph("<b>3.</b> The dependency parser identifies grammatical relationships (nsubj, dobj, prep, ...).", styles["MyBullet"], bulletText=" "))
story.append(Paragraph("<b>4.</b> spaCy's noun chunk rules aggregate related tokens into phrase spans.", styles["MyBullet"], bulletText=" "))
story.append(Preformatted(
    'Input: "The King of Denmark visited flights to London"\n\n'
    'doc = nlp(text)\n'
    'for chunk in doc.noun_chunks:\n'
    '    print(chunk.text)\n\n'
    'Output:\n'
    '  "The King of Denmark"    <-- preposition "of" preserved inside chunk\n'
    '  "flights"                <-- standalone noun\n'
    '  "London"                 <-- proper noun',
    styles["MyCode"],
))

story.append(Paragraph("3.2.2 spaCy Named Entity Recognition (NER)", styles["SubSubHead"]))
story.append(Paragraph(
    "The NER component uses a transition-based neural network model (pre-trained in "
    "<font name='Courier'>en_core_web_sm</font>) that scans the token sequence and "
    "identifies entity boundaries using the BIO tagging scheme (Begin / Inside / Outside). "
    "Each detected entity is assigned a type label: PERSON, ORG, GPE (geo-political entity), "
    "DATE, MONEY, etc.",
    styles["Body"],
))
story.append(Preformatted(
    'Input: "Bitcoin prices on Blockchain.com surged in 2015"\n\n'
    'doc = nlp(text)\n'
    'for ent in doc.ents:\n'
    '    print(ent.text, ent.label_)\n\n'
    'Output:\n'
    '  "Bitcoin"         ORG\n'
    '  "Blockchain.com"  ORG\n'
    '  "2015"            DATE',
    styles["MyCode"],
))

story.append(Paragraph("3.2.3 YAKE Keyphrase Extraction (Statistical)", styles["SubSubHead"]))
story.append(Paragraph(
    "YAKE (Yet Another Keyword Extractor) is an unsupervised, language-independent "
    "keyphrase extraction method. Unlike the syntactic methods above, YAKE uses "
    "statistical features: word position, word frequency, word relatedness to context, "
    "and word case. It extracts n-grams (up to 3 words) ranked by relevance score.",
    styles["Body"],
))
story.append(Paragraph(
    "Key advantage: YAKE naturally preserves stopwords inside meaningful n-grams. "
    "For example, given 'flights to London', YAKE returns the entire phrase as a single "
    "keyphrase rather than splitting it.",
    styles["Body"],
))
story.append(Preformatted(
    'extractor = yake.KeywordExtractor(lan="en", n=3, top=10)\n'
    'keywords = extractor.extract_keywords(\n'
    '    "artificial intelligence security risks in blockchain"\n'
    ')\n'
    '# Returns: [("artificial intelligence security", 0.02),\n'
    '#           ("intelligence security risks", 0.03),\n'
    '#           ("security risks", 0.05), ...]',
    styles["MyCode"],
))

story.append(Paragraph("3.3 Merging and Deduplication", styles["SubHead"]))
story.append(Paragraph(
    "The three sources are merged into a single deduplicated concept list. "
    "YAKE concepts come first (ranked by statistical relevance), followed by "
    "spaCy noun chunks, then named entities. Deduplication is case-insensitive.",
    styles["Body"],
))
story.append(Preformatted(
    'def extract_concepts(text):\n'
    '    yake_concepts = extract_concepts_yake(text)   # statistical keyphrases\n'
    '    noun_chunks   = extract_noun_chunks(text)     # syntactic phrases\n'
    '    entities      = extract_named_entities(text)  # NER entities\n'
    '    \n'
    '    # Merge with case-insensitive deduplication\n'
    '    seen, merged = set(), []\n'
    '    for phrase in yake_concepts + noun_chunks + entities:\n'
    '        key = phrase.lower().strip()\n'
    '        if key and key not in seen:\n'
    '            seen.add(key)\n'
    '            merged.append(phrase)\n'
    '    return merged',
    styles["MyCode"],
))

# ====== 4. SMART STOPWORD REMOVAL ======
story.append(Paragraph("4. Smart Stopword Removal", styles["SectionHead"]))
story.append(Paragraph(
    "Traditional stopword removal blindly deletes common words like 'the', 'a', 'of', "
    "'to', 'be'. This causes problems for meaningful phrases:",
    styles["Body"],
))
story.append(Paragraph('"King of Denmark" becomes "King Denmark" (relationship lost)', styles["MyBullet"], bulletText="\u2022"))
story.append(Paragraph('"flights to London" becomes "flights London" (direction lost)', styles["MyBullet"], bulletText="\u2022"))
story.append(Paragraph('"Let it be" becomes "Let" (phrase nearly destroyed)', styles["MyBullet"], bulletText="\u2022"))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Our smart stopword removal uses noun chunks and named entities from spaCy to identify "
    "'protected spans'. Stopwords inside protected spans are kept; stopwords outside are removed.",
    styles["Body"],
))
story.append(Preformatted(
    'def smart_remove_stopwords(text):\n'
    '    doc = nlp(text)\n'
    '    protected = set()   # token indices inside meaningful phrases\n'
    '    for chunk in doc.noun_chunks:\n'
    '        for token in chunk:\n'
    '            protected.add(token.i)\n'
    '    for ent in doc.ents:\n'
    '        for token in ent:\n'
    '            protected.add(token.i)\n'
    '    \n'
    '    result = []\n'
    '    for token in doc:\n'
    '        if token.i in protected:      # in meaningful phrase -> KEEP\n'
    '            result.append(token.text)\n'
    '        elif token.is_stop:           # loose stopword -> REMOVE\n'
    '            continue\n'
    '        else:\n'
    '            result.append(token.text)  # regular word -> KEEP\n'
    '    return " ".join(result)',
    styles["MyCode"],
))
story.append(make_table(
    ["Input", "Naive Removal", "Smart Removal (Ours)"],
    [
        ["King of Denmark", "King Denmark", "King of Denmark"],
        ["flights to London", "flights London", "flights to London"],
        ["the quick brown fox", "quick brown fox", "quick brown fox"],
    ],
    col_widths=[130, 130, 225],
))
story.append(Spacer(1, 6))

# ====== 5. SOLR INTEGRATION ======
story.append(Paragraph("5. Integration with Solr Search", styles["SectionHead"]))

story.append(Paragraph("5.1 Index-Time Processing", styles["SubHead"]))
story.append(Paragraph(
    "When documents are indexed (<font name='Courier'>prepare_solr_docs.py</font>), each "
    "document's <font name='Courier'>full_text</font> is processed through the NLP pipeline. "
    "Two new fields are added to every Solr document:",
    styles["Body"],
))
story.append(Paragraph(
    "<b>lemmatized_text</b>: spaCy-lemmatized version of full_text, stored as a Solr "
    "<font name='Courier'>text_en</font> field (Porter stemming applied on top).",
    styles["MyBullet"], bulletText="\u2022",
))
story.append(Paragraph(
    "<b>concepts</b>: pipe-separated list of extracted concepts (YAKE + noun chunks + NER), "
    "stored as <font name='Courier'>text_en</font> for full-text searching.",
    styles["MyBullet"], bulletText="\u2022",
))

story.append(Paragraph("5.2 Query-Time Processing", styles["SubHead"]))
story.append(Paragraph(
    "When a user submits a query, the following steps execute in <font name='Courier'>app.py</font>:",
    styles["Body"],
))
story.append(Paragraph("<b>Step 1:</b> The original query is kept as the primary Solr query (<font name='Courier'>q</font> parameter).", styles["MyBullet"], bulletText=" "))
story.append(Paragraph("<b>Step 2:</b> The query is lemmatized with spaCy. If the lemmatized form differs from the original, it is added as a boost query (<font name='Courier'>bq</font>) on the <font name='Courier'>lemmatized_text</font> field.", styles["MyBullet"], bulletText=" "))
story.append(Paragraph("<b>Step 3:</b> Concepts are extracted from the query. The top 5 are added as another boost query on the <font name='Courier'>concepts</font> field.", styles["MyBullet"], bulletText=" "))
story.append(Paragraph("<b>Step 4:</b> eDisMax searches across all fields with configurable weights: <font name='Courier'>title^2, body^1, full_text^3, lemmatized_text^2.5, concepts^2</font>.", styles["MyBullet"], bulletText=" "))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "The boost queries (bq) only affect ranking, never recall &mdash; documents are never "
    "excluded because a boost query did not match.",
    styles["Body"],
))
story.append(Preformatted(
    'Solr Query Parameters:\n'
    '  q  = "artificially intelligent"          (original user input)\n'
    '  qf = "title^2 body full_text^3 lemmatized_text^2.5 concepts^2"\n'
    '  bq = ["lemmatized_text:(artificially intelligent)^2",\n'
    '        \'concepts:("artificially intelligent")^1.5\']',
    styles["MyCode"],
))

# ====== 6. SPELL CORRECTION ======
story.append(PageBreak())
story.append(Paragraph("6. Bonus: Typo Tolerance (Spell Correction + Fuzzy Matching)", styles["SectionHead"]))
story.append(Paragraph(
    "In addition to lemmatization and concept extraction, we implemented typo tolerance "
    "using a two-layer approach:",
    styles["Body"],
))

story.append(Paragraph("6.1 Layer 1: Spell Correction (pyspellchecker)", styles["SubHead"]))
story.append(Paragraph("Uses Peter Norvig's algorithm to generate candidates within Levenshtein edit distance 2.", styles["MyBullet"], bulletText="\u2022"))
story.append(Paragraph("Domain vocabulary from indexed corpus is loaded with boosted frequencies, so terms like 'bitcoin', 'prompt', 'blockchain' are preferred over generic words.", styles["MyBullet"], bulletText="\u2022"))
story.append(Paragraph("Custom candidate ranking using normalised Levenshtein similarity as primary signal and log-frequency as tiebreaker.", styles["MyBullet"], bulletText="\u2022"))
story.append(Paragraph("Corrected query shown as clickable 'Did you mean: ...' suggestion in the UI.", styles["MyBullet"], bulletText="\u2022"))

story.append(Paragraph("6.2 Layer 2: Solr Fuzzy Matching (~N operator)", styles["SubHead"]))
story.append(Paragraph("Appends ~1 to 4-5 character words and ~2 to 6+ character words.", styles["MyBullet"], bulletText="\u2022"))
story.append(Paragraph("Sent as a boost query on full_text &mdash; catches typos that spell correction missed.", styles["MyBullet"], bulletText="\u2022"))
story.append(Paragraph("Quoted phrases are preserved intact (no fuzzy inside quotes).", styles["MyBullet"], bulletText="\u2022"))

story.append(Paragraph("6.3 Spell Correction Test Results", styles["SubHead"]))
story.append(make_table(
    ["Misspelled Input", "Corrected Output", "Status"],
    [
        ["artficial intellgence", "artificial intelligence", "PASS"],
        ["artficially intellgent", "artificially intelligent", "PASS"],
        ["phiscs", "physics", "PASS"],
        ["bitconi blockchain", "bitcoin blockchain", "PASS"],
        ["promt injection", "prompt injection", "PASS"],
        ["criptocurrency", "cryptocurrency", "PASS"],
        ["machne lerning", "machine learning", "PASS"],
        ["securty risks", "security risks", "PASS"],
        ["blokchain technolgy", "blockchain technology", "PASS"],
    ],
    col_widths=[150, 165, 50],
))
story.append(Spacer(1, 8))

# ====== 7. REFERENCES ======
story.append(Paragraph("7. References", styles["SectionHead"]))
refs = [
    "Chrupala, G. (2006). Simple data-driven context-sensitive lemmatization. SEPLN.",
    "Mueller, T., Schmid, H., &amp; Schutze, H. (2015). Joint lemmatization and morphological tagging with Lemming. EMNLP.",
    "Toutanova, K. &amp; Cherry, C. (2009). A global model for joint lemmatization and POS prediction. ACL-IJCNLP.",
    "Snow, R., Jurafsky, D., &amp; Ng, A. Y. (2006). Semantic taxonomy induction from heterogeneous evidence. ACL.",
    "Cambria, E. et al. (2022). SenticNet 7: A commonsense-based neurosymbolic AI framework. LREC.",
    "Zhang, Q. et al. (2016). Keyphrase extraction using deep recurrent neural networks on Twitter. EMNLP.",
    "Meng, R. et al. (2017). Deep keyphrase generation. ACL.",
    "Campos, R. et al. (2020). YAKE! Keyword extraction from single documents. Information Sciences, 509.",
    "Honnibal, M. &amp; Montani, I. (2017). spaCy: Industrial-strength Natural Language Processing in Python.",
    "Norvig, P. (2007). How to write a spelling corrector. norvig.com.",
]
for ref in refs:
    story.append(Paragraph(ref, styles["Ref"]))

# Build PDF
doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=20 * mm,
    rightMargin=20 * mm,
    topMargin=22 * mm,
    bottomMargin=20 * mm,
    title="Lemmatization & Concept Extraction - Implementation Guide",
    author="SC4021 Group",
)
doc.build(story)
print(f"PDF saved to {OUTPUT}")
