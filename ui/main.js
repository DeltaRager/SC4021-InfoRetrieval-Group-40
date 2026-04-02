const ONE_DAY = 86400;
const ONE_WEEK = 604800;
const ONE_MONTH = 2592000;

// ─── CSV Parser ─────────────────────────────────────────────────────────────
// Handles multi-line quoted fields (e.g. Reddit post bodies with newlines)
function parseCSV(text) {
    const rows = [];
    let inQuote = false;
    let field = '';
    let fields = [];

    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        const next = text[i + 1];

        if (ch === '"') {
            if (inQuote && next === '"') { // escaped quote
                field += '"';
                i++;
            } else {
                inQuote = !inQuote;
            }
        } else if (ch === ',' && !inQuote) {
            fields.push(field);
            field = '';
        } else if ((ch === '\n' || (ch === '\r' && next === '\n')) && !inQuote) {
            if (ch === '\r') i++; // skip \r in \r\n
            fields.push(field);
            rows.push(fields);
            fields = [];
            field = '';
        } else {
            field += ch;
        }
    }
    // push last field/row
    if (field || fields.length) {
        fields.push(field);
        rows.push(fields);
    }

    if (rows.length < 2) return [];

    const headers = rows[0].map(h => h.trim());
    return rows.slice(1)
        .filter(r => r.length === headers.length && r.some(f => f.trim()))
        .map(r => {
            const obj = {};
            headers.forEach((h, i) => { obj[h] = r[i] ? r[i].trim() : ''; });
            return obj;
        });
}

// ─── App ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    const searchInput    = document.getElementById('search-input');
    const searchButton   = document.getElementById('search-button');
    const resultsContainer = document.getElementById('results-container');
    const loadingEl      = document.getElementById('loading');
    const loadingText    = document.getElementById('loading-text');
    const filterBtns     = document.querySelectorAll('.filter-btn');
    const timeFilterSelect = document.getElementById('time-filter');
    const searchSection  = document.getElementById('search-section');
    const backNav        = document.getElementById('back-nav');
    const backButton     = document.getElementById('back-button');

    let ALL_DATA = [];          // full dataset from CSV
    let currentFilter    = 'all';
    let currentQuery     = '';
    let currentTimeWindow = 'all';
    let savedResults     = [];

    // ── Load CSV ──────────────────────────────────────────────────────────
    loadingText.innerText = 'Loading Dataset...';
    loadingEl.classList.remove('hidden');

    try {
        const resp = await fetch('/reddit_data.csv');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const text = await resp.text();
        ALL_DATA = parseCSV(text).map(row => ({
            id:          row.id          || '',
            type:        row.type        || 'post',
            parent_id:   row.parent_id   || '',
            title:       row.title       || '',
            text:        row.text        || '',
            author:      row.author      || '[deleted]',
            subreddit:   row.subreddit   || '',
            created_utc: parseInt(row.created_utc) || 0,
            score:       parseInt(row.score)       || 0,
            url:         row.url         || '',
        }));
        console.log(`✅ Loaded ${ALL_DATA.length} records from CSV`);
    } catch (err) {
        console.error('Failed to load CSV:', err);
        resultsContainer.innerHTML = `<div style="text-align:center;color:#ff4500;padding:2rem;">
            ⚠️ Could not load dataset. Make sure <code>reddit_data.csv</code> is in <code>ui/public/</code> and your Vite dev server is running.
        </div>`;
    } finally {
        loadingEl.classList.add('hidden');
    }

    // Initial render — show most upvoted posts
    const topPosts = [...ALL_DATA]
        .filter(d => d.type === 'post')
        .sort((a, b) => b.score - a.score)
        .slice(0, 20);
    savedResults = topPosts;
    renderSearchCards(topPosts);

    // ── Filter & Search Bindings ───────────────────────────────────────────
    filterBtns.forEach(btn => {
        btn.addEventListener('click', e => {
            filterBtns.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentFilter = e.target.getAttribute('data-filter');
            triggerSearch();
        });
    });

    timeFilterSelect.addEventListener('change', e => {
        currentTimeWindow = e.target.value;
        triggerSearch();
    });

    const triggerSearch = () => {
        currentQuery = searchInput.value.trim().toLowerCase();
        performSearch(currentQuery);
    };

    searchButton.addEventListener('click', triggerSearch);
    searchInput.addEventListener('keypress', e => { if (e.key === 'Enter') triggerSearch(); });

    backButton.addEventListener('click', () => {
        backNav.classList.add('hidden');
        searchSection.classList.remove('hidden');
        renderSearchCards(savedResults);
    });

    // ── Time Window Helper ─────────────────────────────────────────────────
    function isWithinTimeWindow(timestampUtc, windowSelection) {
        if (windowSelection === 'all') return true;
        const diff = Math.floor(Date.now() / 1000) - timestampUtc;
        if (windowSelection === 'day')   return diff <= ONE_DAY;
        if (windowSelection === 'week')  return diff <= ONE_WEEK;
        if (windowSelection === 'month') return diff <= ONE_MONTH;
        return true;
    }

    // ── Search Logic ───────────────────────────────────────────────────────
    function performSearch(query) {
        resultsContainer.innerHTML = '';
        loadingText.innerText = 'Searching...';
        loadingEl.classList.remove('hidden');
        backNav.classList.add('hidden');
        searchSection.classList.remove('hidden');

        setTimeout(() => {
            loadingEl.classList.add('hidden');

            let filtered;
            if (!query) {
                // No query — show top posts/comments depending on filter
                filtered = [...ALL_DATA]
                    .filter(item => {
                        const typeMatch = currentFilter === 'all' || item.type === currentFilter;
                        const timeMatch = isWithinTimeWindow(item.created_utc, currentTimeWindow);
                        return typeMatch && timeMatch;
                    })
                    .sort((a, b) => b.score - a.score)
                    .slice(0, 20);
            } else {
                filtered = ALL_DATA.filter(item => {
                    const textMatch = item.text.toLowerCase().includes(query) ||
                                      item.title.toLowerCase().includes(query);
                    const typeMatch = currentFilter === 'all' || item.type === currentFilter;
                    const timeMatch = isWithinTimeWindow(item.created_utc, currentTimeWindow);
                    return textMatch && typeMatch && timeMatch;
                }).sort((a, b) => b.score - a.score);
            }

            savedResults = filtered;
            renderSearchCards(filtered);
        }, 300);
    }

    // ── Render Cards ───────────────────────────────────────────────────────
    function renderSearchCards(data) {
        resultsContainer.innerHTML = '';
        if (data.length === 0) {
            resultsContainer.innerHTML = `<div style="text-align:center;color:var(--text-secondary);padding:2rem;">
                No results found${currentQuery ? ` for "<strong>${currentQuery}</strong>"` : ''}.
            </div>`;
            return;
        }

        // Render up to 50 results for performance
        data.slice(0, 50).forEach((item, index) => {
            const card = createCardHTML(item, index, false);
            if (item.type === 'post') {
                card.classList.add('clickable');
                card.title = 'Click to view comments';
                card.addEventListener('click', () => openPostDetail(item));
            }
            resultsContainer.appendChild(card);
        });

        if (data.length > 50) {
            const note = document.createElement('div');
            note.style.cssText = 'text-align:center;color:var(--text-secondary);padding:1rem;font-size:0.85rem;';
            note.innerText = `Showing top 50 of ${data.length} results. Refine your search to narrow results.`;
            resultsContainer.appendChild(note);
        }
    }

    // ── Post Detail View ───────────────────────────────────────────────────
    function openPostDetail(postItem) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        resultsContainer.innerHTML = '';
        searchSection.classList.add('hidden');
        backNav.classList.remove('hidden');
        loadingText.innerText = 'Loading Comments...';
        loadingEl.classList.remove('hidden');

        setTimeout(() => {
            loadingEl.classList.add('hidden');

            const postCard = createCardHTML(postItem, 0, true);
            postCard.classList.add('focused-post');
            resultsContainer.appendChild(postCard);

            const comments = ALL_DATA.filter(item =>
                item.type === 'comment' && item.parent_id === postItem.id
            ).sort((a, b) => b.score - a.score);

            if (comments.length === 0) {
                const emptyMsg = document.createElement('div');
                emptyMsg.className = 'comment-card last-comment';
                emptyMsg.style.color = 'var(--text-secondary)';
                emptyMsg.innerText = 'No comments found for this post.';
                resultsContainer.appendChild(emptyMsg);
            } else {
                comments.forEach((comment, index) => {
                    const cCard = createCardHTML(comment, index + 1, true);
                    cCard.classList.remove('result-card');
                    cCard.classList.add('comment-card');
                    if (index === comments.length - 1) cCard.classList.add('last-comment');
                    resultsContainer.appendChild(cCard);
                });
            }
        }, 200);
    }

    // ── Card HTML Builder ──────────────────────────────────────────────────
    function timeAgo(utc) {
        const diff = Math.floor(Date.now() / 1000) - utc;
        if (diff < 3600)    return Math.floor(diff / 60) + ' min. ago';
        if (diff < 86400)   return Math.floor(diff / 3600) + ' hr. ago';
        if (diff < 2592000) return Math.floor(diff / 86400) + ' days ago';
        return Math.floor(diff / 2592000) + ' mo. ago';
    }

    function createCardHTML(item, index, detailedView) {
        const dateStr = timeAgo(item.created_utc);
        const card = document.createElement('div');
        card.className = 'result-card';
        card.style.animationDelay = detailedView ? '0s' : `${index * 0.04}s`;

        const numComments = item.type === 'post'
            ? ALL_DATA.filter(c => c.parent_id === item.id).length
            : 0;

        const badgeClass = item.type === 'post' ? 'post' : 'comment';
        const typeLabel  = item.type === 'post' ? 'POST'  : 'COMMENT';

        card.innerHTML = `
            <div class="card-header">
                <span class="badge ${badgeClass}">${typeLabel}</span>
                <div class="meta" style="margin-left:auto;">
                    <span class="score">↑ ${item.score.toLocaleString()}</span>
                    <span style="color:var(--text-primary);font-weight:500;">u/${item.author}</span>
                    ${item.subreddit ? `<span style="color:var(--reddit-orange);font-weight:700;">r/${item.subreddit}</span>` : ''}
                    <span>• ${dateStr}</span>
                </div>
            </div>
            ${item.title ? `<h3 class="card-title">${highlightQuery(item.title, !detailedView ? currentQuery : '')}</h3>` : ''}
            <p class="card-text">${highlightQuery(item.text, !detailedView ? currentQuery : '')}</p>
            <div class="action-row">
                ${item.type === 'post' ? `<div>💬 ${numComments} Comments</div>` : ''}
                ${item.url ? `<a href="${item.url}" target="_blank" style="color:var(--text-primary);text-decoration:none;">🔗 View on Reddit</a>` : ''}
            </div>
        `;
        return card;
    }

    function highlightQuery(text, query) {
        if (!query || !text) return text;
        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escaped})`, 'gi');
        return text.replace(regex, '<mark style="background:rgba(255,69,0,0.4);color:white;border-radius:2px;padding:0 4px">$1</mark>');
    }
});
