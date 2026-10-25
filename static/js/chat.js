/**
 * chat.js — Smart College Assistant frontend logic.
 *
 * Handles:
 *  - Sidebar navigation between views (Chat / FAQs / History / Feedback / About)
 *  - Quick-topic sidebar buttons & right-panel quick links (send directly to chat)
 *  - Category card clicks & suggested question clicks
 *  - Chat message sending via fetch /api/chat
 *  - XSS-safe rendering (textContent only, never innerHTML for user data)
 *  - Loading indicator, error banner
 *  - Feedback buttons (👍 / 👎) on each bot reply
 *  - FAQ accordion view (loaded from /api/faqs, live filter)
 *  - History view (loaded from /api/history)
 *  - Feedback form (standalone form in Feedback view)
 *  - Auto-resize textarea, Enter-to-send, Shift+Enter for newline
 */

(function () {
  'use strict';

  /* ─────────────────────────────────────────────────────────────────
     DOM references
  ───────────────────────────────────────────────────────────────── */
  const msgInput      = document.getElementById('msgInput');
  const sendBtn       = document.getElementById('sendBtn');
  const messagesEl    = document.getElementById('messages');
  const welcomeScreen = document.getElementById('welcomeScreen');
  const errorBar      = document.getElementById('errorBar');
  const errorMsg      = document.getElementById('errorMsg');
  const errorClose    = document.getElementById('errorClose');

  // Sidebar nav items
  const navItems      = document.querySelectorAll('.nav-item[data-view]');

  // Category cards, suggested buttons, quick links, quick-topic sidebar btns
  const catCards      = document.querySelectorAll('.cat-card[data-query]');
  const suggestedBtns = document.querySelectorAll('.suggested-btn[data-query]');
  const quickLinks    = document.querySelectorAll('.quick-link[data-query]');
  const quickTopics   = document.querySelectorAll('.nav-item[data-quicktopic]');

  // FAQ view
  const faqList       = document.getElementById('faqList');
  const faqFilter     = document.getElementById('faqFilterInput');

  // History view
  const historyList   = document.getElementById('historyList');

  // Feedback view
  const ratingBtns       = document.querySelectorAll('.rating-btn');
  const feedbackComment  = document.getElementById('feedbackComment');
  const submitFeedbackBtn= document.getElementById('submitFeedbackBtn');
  const feedbackResult   = document.getElementById('feedbackResult');

  /* ─────────────────────────────────────────────────────────────────
     State
  ───────────────────────────────────────────────────────────────── */
  let chatStarted      = false;
  let loadingEl        = null;
  let selectedRating   = null;
  let faqsLoaded       = false;
  let allFaqs          = [];    // cache for filter

  /* ─────────────────────────────────────────────────────────────────
     Utilities
  ───────────────────────────────────────────────────────────────── */

  function formatTime(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  /** Create a text node element — never use innerHTML with user data */
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls)  e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function scrollBottom() {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function showError(msg) {
    errorMsg.textContent = msg;
    errorBar.hidden = false;
    clearTimeout(showError._t);
    showError._t = setTimeout(() => { errorBar.hidden = true; }, 7000);
  }

  function hideError() { errorBar.hidden = true; }

  function resizeTextarea() {
    msgInput.style.height = 'auto';
    msgInput.style.height = Math.min(msgInput.scrollHeight, 110) + 'px';
  }

  /* ─────────────────────────────────────────────────────────────────
     Sidebar navigation
  ───────────────────────────────────────────────────────────────── */

  function activateView(viewName) {
    // Update nav items
    navItems.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === viewName);
      btn.setAttribute('aria-current', btn.dataset.view === viewName ? 'page' : 'false');
    });

    // Show/hide view panels
    document.querySelectorAll('.view-panel').forEach(panel => {
      panel.classList.toggle('active', panel.id === 'view-' + viewName);
    });

    // Load FAQs and history when those views are opened.
    // FAQs: re-render from cache every visit (so it looks consistent),
    //       but re-fetch from server to pick up any admin changes.
    if (viewName === 'faqs') {
      if (faqsLoaded) {
        // Re-render immediately from cache so the view looks clean,
        // then silently refresh from the server in the background.
        faqFilter.value = '';          // clear any leftover search text
        renderFAQs(allFaqs);
        refreshFAQs();
      } else {
        loadFAQs();
      }
    }
    if (viewName === 'history') loadHistory();
  }

  navItems.forEach(btn => {
    btn.addEventListener('click', () => activateView(btn.dataset.view));
  });

  /* ─────────────────────────────────────────────────────────────────
     Chat: render messages
  ───────────────────────────────────────────────────────────────── */

  function appendMessage(role, text, faqId = null) {
    // Hide welcome screen on first message
    if (!chatStarted && welcomeScreen) {
      welcomeScreen.style.display = 'none';
      chatStarted = true;
    }

    const row    = el('div', `msg-row msg-row--${role}`);
    const avatar = el('div', 'msg-avatar', role === 'user' ? '🧑' : '🤖');
    avatar.setAttribute('aria-hidden', 'true');

    const inner  = el('div', 'msg-inner');
    const bubble = el('div', 'msg-bubble', text);
    const meta   = el('div', 'msg-meta', formatTime(new Date()));
    meta.setAttribute('aria-label', `Sent at ${formatTime(new Date())}`);

    inner.appendChild(bubble);
    inner.appendChild(meta);

    // Feedback buttons for bot messages
    if (role === 'bot' && faqId !== null) {
      inner.appendChild(buildFbRow(faqId));
    }

    row.appendChild(avatar);
    row.appendChild(inner);
    messagesEl.appendChild(row);
    scrollBottom();
    return row;
  }

  function buildFbRow(faqId) {
    const row  = el('div', 'fb-row');
    row.setAttribute('aria-label', 'Was this answer helpful?');

    const yes  = el('button', 'fb-btn', '👍 Helpful');
    yes.setAttribute('aria-label', 'Mark as helpful');
    const no   = el('button', 'fb-btn', '👎 Not helpful');
    no.setAttribute('aria-label', 'Mark as not helpful');

    async function vote(rating, clicked, other) {
      clicked.classList.add('fb-selected');
      clicked.disabled = true;
      other.disabled   = true;
      try {
        await fetch('/api/feedback', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ faq_id: faqId, rating, comment: '' }),
        });
        row.innerHTML = '';
        const thanks = el('span', 'fb-btn fb-thanks', '✓ Thanks for your feedback!');
        row.appendChild(thanks);
      } catch (_) {
        clicked.classList.remove('fb-selected');
        clicked.disabled = false;
        other.disabled   = false;
      }
    }

    yes.addEventListener('click', () => vote(1, yes, no));
    no.addEventListener('click',  () => vote(0, no,  yes));
    row.appendChild(yes);
    row.appendChild(no);
    return row;
  }

  /* ─────────────────────────────────────────────────────────────────
     Chat: loading indicator
  ───────────────────────────────────────────────────────────────── */

  function showLoading() {
    loadingEl = document.createElement('div');
    loadingEl.className = 'loading-row';
    loadingEl.setAttribute('role', 'status');
    loadingEl.setAttribute('aria-label', 'Assistant is thinking');

    const avatar = el('div', 'msg-avatar', '🤖');
    avatar.setAttribute('aria-hidden', 'true');

    const dotsWrap = el('div', 'dots');
    dotsWrap.setAttribute('aria-hidden', 'true');
    [1,2,3].forEach(() => dotsWrap.appendChild(el('span')));

    const sr = el('span', 'sr-only', 'Thinking…');

    loadingEl.appendChild(avatar);
    loadingEl.appendChild(dotsWrap);
    loadingEl.appendChild(sr);
    messagesEl.appendChild(loadingEl);
    scrollBottom();
  }

  function hideLoading() {
    if (loadingEl) { loadingEl.remove(); loadingEl = null; }
  }

  /* ─────────────────────────────────────────────────────────────────
     Chat: send message
  ───────────────────────────────────────────────────────────────── */

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (trimmed.length > 500) {
      showError('Your message is too long. Please keep it under 500 characters.');
      return;
    }

    // Switch to chat view if not there
    activateView('chat');
    hideError();

    appendMessage('user', trimmed);
    msgInput.value = '';
    resizeTextarea();
    sendBtn.disabled = true;
    showLoading();

    try {
      const res = await fetch('/api/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: trimmed }),
      });

      hideLoading();

      if (!res.ok) {
        let errText = `Server error (${res.status}). Please try again.`;
        try { const d = await res.json(); if (d.error) errText = d.error; } catch (_) {}
        showError(errText);
        appendMessage('bot', 'Sorry, something went wrong. Please try again.', null);
        return;
      }

      const data = await res.json();
      appendMessage('bot', data.answer, data.faq_id ?? null);

    } catch (_) {
      hideLoading();
      showError('Could not reach the server. Please check your connection.');
      appendMessage('bot', "I'm having trouble connecting. Please try again in a moment.", null);
    } finally {
      sendBtn.disabled = false;
      msgInput.focus();
    }
  }

  /* ─────────────────────────────────────────────────────────────────
     Chat: input event listeners
  ───────────────────────────────────────────────────────────────── */

  sendBtn.addEventListener('click', () => sendMessage(msgInput.value));

  msgInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(msgInput.value);
    }
  });

  msgInput.addEventListener('input', resizeTextarea);

  errorClose.addEventListener('click', hideError);

  /* ─────────────────────────────────────────────────────────────────
     Category cards, suggested questions, quick links, quick topics
  ───────────────────────────────────────────────────────────────── */

  function fireQuery(query) {
    msgInput.value = query;
    resizeTextarea();
    sendMessage(query);
  }

  catCards.forEach(btn      => btn.addEventListener('click', () => fireQuery(btn.dataset.query)));
  suggestedBtns.forEach(btn => btn.addEventListener('click', () => fireQuery(btn.dataset.query)));
  quickLinks.forEach(btn    => btn.addEventListener('click', () => fireQuery(btn.dataset.query)));
  quickTopics.forEach(btn   => btn.addEventListener('click', () => fireQuery(btn.dataset.quicktopic)));

  /* ─────────────────────────────────────────────────────────────────
     FAQ view — load from /api/faqs and render accordion
  ───────────────────────────────────────────────────────────────── */

  async function loadFAQs() {
    faqList.innerHTML = '';
    const loading = el('p', null, 'Loading FAQs…');
    loading.style.color = 'var(--muted)';
    loading.style.fontSize = '.85rem';
    faqList.appendChild(loading);

    try {
      const res  = await fetch('/api/faqs');
      const data = await res.json();
      allFaqs = data.faqs || [];
      renderFAQs(allFaqs);
      faqsLoaded = true;

      // Update badge
      const badge = document.getElementById('faqCountBadge');
      if (badge) badge.textContent = allFaqs.length;

    } catch (_) {
      faqList.innerHTML = '';
      const err = el('p', null, 'Failed to load FAQs. Please try again.');
      err.style.color = 'var(--danger)';
      faqList.appendChild(err);
    }
  }

  /** Silent background refresh — updates cache & re-renders without showing a loading state */
  async function refreshFAQs() {
    try {
      const res  = await fetch('/api/faqs');
      const data = await res.json();
      const fresh = data.faqs || [];
      // Only re-render if something actually changed
      if (JSON.stringify(fresh) !== JSON.stringify(allFaqs)) {
        allFaqs = fresh;
        renderFAQs(allFaqs);
        const badge = document.getElementById('faqCountBadge');
        if (badge) badge.textContent = allFaqs.length;
      }
    } catch (_) {
      // Silently ignore — user already sees cached data
    }
  }

  function renderFAQs(faqs) {
    faqList.innerHTML = '';
    if (!faqs.length) {
      faqList.appendChild(el('p', null, 'No FAQs found.'));
      return;
    }

    // Group by category
    const groups = {};
    faqs.forEach(f => { (groups[f.category] = groups[f.category] || []).push(f); });

    const catIcons = {
      'Admissions':   '📝',
      'Courses':      '📚',
      'Fees':         '💰',
      'Examinations': '📅',
      'Facilities':   '🏛',
      'General':      'ℹ️',
    };

    Object.keys(groups).sort().forEach(cat => {
      const section = el('div', 'faq-category-section');

      const heading = el('div', 'faq-cat-heading');
      heading.textContent = (catIcons[cat] || '📌') + ' ' + cat;
      const countBadge = el('span', 'faq-cat-count', groups[cat].length.toString());
      heading.appendChild(countBadge);
      section.appendChild(heading);

      const accordion = el('div', 'faq-accordion');
      accordion.setAttribute('role', 'list');

      groups[cat].forEach(faq => {
        const item = el('div', 'faq-item');
        item.setAttribute('role', 'listitem');

        const qEl = el('button', 'faq-question');
        qEl.setAttribute('aria-expanded', 'false');
        const qText = el('span', null, faq.question);
        const chevron = el('span', 'faq-chevron', '▼');
        qEl.appendChild(qText);
        qEl.appendChild(chevron);

        const aEl = el('div', 'faq-answer', faq.answer);

        qEl.addEventListener('click', () => {
          const isOpen = qEl.classList.contains('open');
          // Close all others in same accordion
          accordion.querySelectorAll('.faq-question.open').forEach(q => {
            q.classList.remove('open');
            q.setAttribute('aria-expanded', 'false');
            q.nextElementSibling.classList.remove('open');
          });
          if (!isOpen) {
            qEl.classList.add('open');
            qEl.setAttribute('aria-expanded', 'true');
            aEl.classList.add('open');
          }
        });

        item.appendChild(qEl);
        item.appendChild(aEl);
        accordion.appendChild(item);
      });

      section.appendChild(accordion);
      faqList.appendChild(section);
    });
  }

  // Live FAQ filter
  if (faqFilter) {
    faqFilter.addEventListener('input', () => {
      const q = faqFilter.value.toLowerCase().trim();
      if (!q) { renderFAQs(allFaqs); return; }
      const filtered = allFaqs.filter(f =>
        f.question.toLowerCase().includes(q) ||
        f.answer.toLowerCase().includes(q)   ||
        f.keywords.toLowerCase().includes(q)
      );
      renderFAQs(filtered);
    });
  }

  /* ─────────────────────────────────────────────────────────────────
     History view — load from /api/history
  ───────────────────────────────────────────────────────────────── */

  async function loadHistory() {
    historyList.innerHTML = '';
    const loading = el('p', null, 'Loading history…');
    loading.style.color = 'var(--muted)';
    loading.style.fontSize = '.85rem';
    historyList.appendChild(loading);

    try {
      const res  = await fetch('/api/history');
      const data = await res.json();
      const items = data.history || [];

      historyList.innerHTML = '';

      if (!items.length) {
        const empty = el('div', 'history-empty');
        const icon  = el('div', 'history-empty-icon', '💬');
        icon.setAttribute('aria-hidden', 'true');
        const msg   = el('p', null, 'No conversation history yet.\nStart chatting to see your history here.');
        empty.appendChild(icon);
        empty.appendChild(msg);
        historyList.appendChild(empty);
        return;
      }

      const list = el('div', 'history-list');
      items.forEach(item => {
        const card  = el('div', 'history-item');

        const qRow  = el('div', 'history-q');
        qRow.appendChild(el('span', null, item.user_message));

        const aRow  = el('div', 'history-a');
        aRow.appendChild(el('span', null, item.bot_response));

        const time  = el('div', 'history-time', item.created_at || '');

        card.appendChild(qRow);
        card.appendChild(aRow);
        card.appendChild(time);
        list.appendChild(card);
      });

      historyList.appendChild(list);

    } catch (_) {
      historyList.innerHTML = '';
      const err = el('p', null, 'Failed to load history. Please try again.');
      err.style.color = 'var(--danger)';
      historyList.appendChild(err);
    }
  }

  /* ─────────────────────────────────────────────────────────────────
     Feedback form (standalone view)
  ───────────────────────────────────────────────────────────────── */

  ratingBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      selectedRating = parseInt(btn.dataset.rating, 10);
      ratingBtns.forEach(b => {
        b.classList.toggle('selected', b === btn);
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
    });
  });

  if (submitFeedbackBtn) {
    submitFeedbackBtn.addEventListener('click', async () => {
      if (selectedRating === null) {
        feedbackResult.style.color = 'var(--danger)';
        feedbackResult.textContent = 'Please select a rating before submitting.';
        return;
      }

      submitFeedbackBtn.disabled = true;
      feedbackResult.textContent = '';

      try {
        const res = await fetch('/api/feedback', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            faq_id:  null,
            rating:  selectedRating,
            comment: feedbackComment ? feedbackComment.value.trim() : '',
          }),
        });
        const data = await res.json();
        if (data.success) {
          feedbackResult.style.color = 'var(--success)';
          feedbackResult.textContent = '✓ Thank you for your feedback!';
          if (feedbackComment) feedbackComment.value = '';
          selectedRating = null;
          ratingBtns.forEach(b => { b.classList.remove('selected'); b.setAttribute('aria-pressed','false'); });
        } else {
          feedbackResult.style.color = 'var(--danger)';
          feedbackResult.textContent = 'Something went wrong. Please try again.';
        }
      } catch (_) {
        feedbackResult.style.color = 'var(--danger)';
        feedbackResult.textContent = 'Could not connect. Please try again.';
      } finally {
        submitFeedbackBtn.disabled = false;
      }
    });
  }

  /* ─────────────────────────────────────────────────────────────────
     Init
  ───────────────────────────────────────────────────────────────── */
  msgInput.focus();

})();
