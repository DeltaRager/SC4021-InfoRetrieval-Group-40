// Dynamic timestamps so our Time filter mock data works perfectly
const NOW = Math.floor(Date.now() / 1000);
const ONE_HOUR = 3600;
const ONE_DAY = 86400;
const ONE_WEEK = 604800;
const ONE_MONTH = 2592000;

// Mock Data mimicking a Solr Response
const MOCK_DATA = [
    {
        id: "t3_1ab2c3d",
        type: "post",
        title: "ChatGPT just passed the bar exam",
        text: "I can't believe how fast AI is progressing. What does this mean for lawyers? Will junior associates be replaced soon, or is this just hype?",
        author: "ai_fanatic",
        subreddit: "technology",
        score: 1540,
        created_utc: NOW - (2 * ONE_HOUR), // 2 hours ago
        url: "https://reddit.com/r/technology/comments/1ab2c3d"
    },
    {
        id: "t1_d9efg5i",
        type: "comment",
        parent_id: "t3_1ab2c3d",
        title: "",
        text: "I just use it to draft emails, and honestly it saves me 2 hours a day. Highly recommend for pure productivity, but I wouldn't trust it for legal cases yet.",
        author: "productivity_guru",
        subreddit: "technology",
        score: 320,
        created_utc: NOW - (1 * ONE_HOUR)
    },
    {
        id: "t1_d9exxx",
        type: "comment",
        parent_id: "t3_1ab2c3d",
        title: "",
        text: "As a lawyer, I find it useful for summarizing long documents, but it hallucinates cases which is incredibly dangerous.",
        author: "skeptic_lawyer",
        subreddit: "technology",
        score: 125,
        created_utc: NOW - (30 * 60) // 30 mins ago
    },
    {
        id: "t3_9xyz890",
        type: "post",
        title: "Is Midjourney ruining digital art?",
        text: "Every time I go on ArtStation now, it's flooded with AI generations. It feels like real artists who spent years honing their craft are being pushed out by prompt engineers.",
        author: "tired_artist",
        subreddit: "Art",
        score: 890,
        created_utc: NOW - (5 * ONE_DAY), // 5 days ago
        url: "https://reddit.com/r/Art/comments/9xyz890"
    },
    {
        id: "t1_z8a9b1c",
        type: "comment",
        parent_id: "t3_9xyz890",
        title: "",
        text: "I think it's just a new tool. Photography didn't kill painting, it just changed it. Artists will adapt and use AI in their workflows.",
        author: "tech_optimist",
        subreddit: "Art",
        score: 210,
        created_utc: NOW - (4 * ONE_DAY)
    },
    {
        id: "t3_old_ai",
        type: "post",
        title: "I think AI is a fad",
        text: "People have been talking about artificial intelligence changing the world since the 80s. Nothing really fundamentally changes.",
        author: "cranky_guy",
        subreddit: "artificial",
        score: -15,
        created_utc: NOW - (3 * ONE_MONTH), // 3 months ago (wont show up in recent filters)
        url: "https://reddit.com/r/technology/comments/old_ai"
    }
];

document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');
    const resultsContainer = document.getElementById('results-container');
    const loadingEl = document.getElementById('loading');
    const loadingText = document.getElementById('loading-text');
    const filterBtns = document.querySelectorAll('.filter-btn');
    const timeFilterSelect = document.getElementById('time-filter');
    
    const searchSection = document.getElementById('search-section');
    const backNav = document.getElementById('back-nav');
    const backButton = document.getElementById('back-button');

    let currentFilter = 'all'; // all, post, comment
    let currentQuery = '';
    let currentTimeWindow = 'all'; 
    let savedResults = [];

    // Navigation and Filtering Logic
    filterBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            filterBtns.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            
            currentFilter = e.target.getAttribute('data-filter');
            triggerSearch();
        });
    });

    timeFilterSelect.addEventListener('change', (e) => {
        currentTimeWindow = e.target.value;
        triggerSearch();
    });

    const triggerSearch = () => {
        currentQuery = searchInput.value.trim().toLowerCase();
        performSearch(currentQuery);
    };

    searchButton.addEventListener('click', triggerSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') triggerSearch();
    });
    
    backButton.addEventListener('click', () => {
        backNav.classList.add('hidden');
        searchSection.classList.remove('hidden');
        renderSearchCards(savedResults);
    });

    // Helper to evaluate time window
    function isWithinTimeWindow(timestampUtc, windowSelection) {
        if (windowSelection === 'all') return true;
        const currentUnix = Math.floor(Date.now() / 1000);
        const diff = currentUnix - timestampUtc;
        
        if (windowSelection === 'day') return diff <= ONE_DAY;
        if (windowSelection === 'week') return diff <= ONE_WEEK;
        if (windowSelection === 'month') return diff <= ONE_MONTH;
        return true;
    }

    function performSearch(query) {
        resultsContainer.innerHTML = '';
        loadingText.innerText = 'Analyzing Opinions...';
        loadingEl.classList.remove('hidden');
        backNav.classList.add('hidden');
        searchSection.classList.remove('hidden');

        // Simulate Network Request Delay for Solr
        setTimeout(() => {
            loadingEl.classList.add('hidden');
            
            const filtered = MOCK_DATA.filter(item => {
                const textMatch = item.text.toLowerCase().includes(query) || (item.title && item.title.toLowerCase().includes(query));
                const typeMatch = currentFilter === 'all' || item.type === currentFilter;
                const timeMatch = isWithinTimeWindow(item.created_utc, currentTimeWindow);
                return textMatch && typeMatch && timeMatch;
            });

            savedResults = filtered;
            renderSearchCards(filtered);
        }, 600);
    }

    function renderSearchCards(data) {
        resultsContainer.innerHTML = '';

        if (data.length === 0) {
            resultsContainer.innerHTML = `<div style="text-align: center; color: var(--text-secondary); padding: 2rem;">No results found for "${currentQuery}" in this context.</div>`;
            return;
        }

        data.forEach((item, index) => {
            const card = createCardHTML(item, index, false);
            
            if (item.type === 'post') {
                card.classList.add('clickable');
                card.title = "Click to view comments";
                card.addEventListener('click', () => {
                    openPostDetail(item);
                });
            }
            
            resultsContainer.appendChild(card);
        });
    }

    function openPostDetail(postItem) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        
        resultsContainer.innerHTML = '';
        searchSection.classList.add('hidden');
        backNav.classList.remove('hidden');
        loadingText.innerText = 'Loading Comments...';
        loadingEl.classList.remove('hidden');
        
        // Simulate fetch delay to get comments for this post
        setTimeout(() => {
            loadingEl.classList.add('hidden');
            
            const postCard = createCardHTML(postItem, 0, true);
            postCard.classList.add('focused-post');
            resultsContainer.appendChild(postCard);
            
            const comments = MOCK_DATA.filter(item => item.type === 'comment' && item.parent_id === postItem.id);
            
            if (comments.length === 0) {
                const emptyMsg = document.createElement('div');
                emptyMsg.className = 'comment-card last-comment';
                emptyMsg.style.color = 'var(--text-secondary)';
                emptyMsg.innerText = 'No comments found.';
                resultsContainer.appendChild(emptyMsg);
            } else {
                comments.forEach((comment, index) => {
                    const cCard = createCardHTML(comment, index + 1, true);
                    cCard.classList.remove('result-card');
                    cCard.classList.add('comment-card');
                    if (index === comments.length - 1) {
                        cCard.classList.add('last-comment');
                    }
                    resultsContainer.appendChild(cCard);
                });
            }
        }, 300);
    }

    // Helper functions
    function timeAgo(utc) {
        const diff = Math.floor(Date.now() / 1000) - utc;
        if (diff < 3600) return Math.floor(diff/60) + ' min. ago';
        if (diff < 86400) return Math.floor(diff/3600) + ' hr. ago';
        if (diff < 2592000) return Math.floor(diff/86400) + ' days ago';
        return Math.floor(diff/2592000) + ' mo. ago';
    }

    function createCardHTML(item, index, detailedView) {
        const dateStr = timeAgo(item.created_utc);
        const animationDelay = detailedView ? '0s' : `${index * 0.05}s`;

        const card = document.createElement('div');
        card.className = 'result-card';
        card.style.animationDelay = animationDelay;
        
        let numComments = item.type === 'post' ? MOCK_DATA.filter(c => c.parent_id === item.id).length : 0;
        
        const badgeClass = item.type === 'post' ? 'post' : 'comment';
        const typeLabel = item.type === 'post' ? 'POST' : 'COMMENT';

        card.innerHTML = `
            <div class="card-header">
                <span class="badge ${badgeClass}">${typeLabel}</span>
                <div class="meta" style="margin-left: auto;">
                    <span class="score">↑ ${item.score}</span>
                    <span style="color: var(--text-primary); font-weight: 500;">u/${item.author}</span>
                    <span style="color: var(--reddit-orange); font-weight: 700;">r/${item.subreddit}</span>
                    <span>• ${dateStr}</span>
                </div>
            </div>
            ${item.title ? `<h3 class="card-title">${highlightQuery(item.title, !detailedView ? currentQuery : '')}</h3>` : ''}
            <p class="card-text">${highlightQuery(item.text, !detailedView ? currentQuery : '')}</p>
            <div class="action-row">
                ${item.type === 'post' ? `<div>💬 ${numComments} Comments</div>` : ''}
                ${item.url ? `<div><a href="${item.url}" target="_blank" style="color: var(--text-primary); font-weight: normal; text-decoration: none;">🔗 Redirect Link</a></div>` : ''}
            </div>
        `;
        return card;
    }

    function highlightQuery(text, query) {
        if (!query) return text;
        const regex = new RegExp(`(${query})`, 'gi');
        return text.replace(regex, '<mark style="background: rgba(255, 69, 0, 0.4); color: white; border-radius: 2px; padding: 0 4px">$1</mark>');
    }

    // Initial render
    renderSearchCards(MOCK_DATA);
});
