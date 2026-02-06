(() => {
  const DEFAULT_FILTER = 'all';
  const STORAGE_KEY = 'publicationFilter';
  const QUERY_KEY = 'pub';
  const BUTTON_SELECTOR = '.pub-button';
  const CARD_SELECTOR = '.publication-card';
  const VIDEO_SELECTOR = `${CARD_SELECTOR} video`;

  const reducedMotionMedia =
    typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : null;

  let activeFilter = DEFAULT_FILTER;
  let videoObserver = null;

  function sanitizeFilter(type) {
    return type === 'featured' ? 'featured' : DEFAULT_FILTER;
  }

  function getFilterButtons() {
    return document.querySelectorAll(BUTTON_SELECTOR);
  }

  function getPublicationCards() {
    return document.querySelectorAll(CARD_SELECTOR);
  }

  function getPublicationVideos() {
    return document.querySelectorAll(VIDEO_SELECTOR);
  }

  function prefersReducedMotion() {
    return Boolean(reducedMotionMedia && reducedMotionMedia.matches);
  }

  function readFilterFromQuery() {
    const queryFilter = new URLSearchParams(window.location.search).get(QUERY_KEY);
    return queryFilter ? sanitizeFilter(queryFilter) : null;
  }

  function setFilterQuery(type) {
    const url = new URL(window.location.href);
    if (type === DEFAULT_FILTER) {
      url.searchParams.delete(QUERY_KEY);
    } else {
      url.searchParams.set(QUERY_KEY, type);
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function loadSavedFilter() {
    try {
      return sanitizeFilter(window.localStorage.getItem(STORAGE_KEY));
    } catch (error) {
      return DEFAULT_FILTER;
    }
  }

  function persistFilter(type) {
    try {
      window.localStorage.setItem(STORAGE_KEY, type);
    } catch (error) {
    }
  }

  function setButtonStates(type) {
    getFilterButtons().forEach((button) => {
      const isActive = button.dataset.filter === type;
      button.classList.toggle('active', isActive);
      button.setAttribute('aria-pressed', String(isActive));
    });
  }

  function setCardVisibility(type) {
    getPublicationCards().forEach((card) => {
      const shouldShow = type === DEFAULT_FILTER || card.classList.contains('featured');
      card.hidden = !shouldShow;
    });
  }

  function setVideoPlayback(video, shouldPlay) {
    if (!shouldPlay) {
      video.pause();
      return;
    }

    const playPromise = video.play();
    if (playPromise && typeof playPromise.catch === 'function') {
      playPromise.catch(() => {});
    }
  }

  function syncVisibleVideoPlayback() {
    const shouldPlay = !prefersReducedMotion();

    getPublicationVideos().forEach((video) => {
      const card = video.closest(CARD_SELECTOR);
      const isVisible = Boolean(card && !card.hidden);

      if (!isVisible) {
        setVideoPlayback(video, false);
        return;
      }

      if (!videoObserver) {
        setVideoPlayback(video, shouldPlay);
      }
    });
  }

  function createVideoObserver() {
    if (prefersReducedMotion() || typeof window.IntersectionObserver !== 'function') {
      videoObserver = null;
      syncVisibleVideoPlayback();
      return;
    }

    videoObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const card = entry.target.closest(CARD_SELECTOR);
          const isVisible = Boolean(card && !card.hidden);
          setVideoPlayback(entry.target, entry.isIntersecting && isVisible);
        });
      },
      { threshold: 0.25 }
    );

    getPublicationVideos().forEach((video) => videoObserver.observe(video));
    syncVisibleVideoPlayback();
  }

  function resetVideoObserver() {
    if (videoObserver) {
      videoObserver.disconnect();
      videoObserver = null;
    }

    createVideoObserver();
  }

  function applyFilter(type, options = {}) {
    const filter = sanitizeFilter(type);
    const shouldPersist = options.persist !== false;
    const shouldUpdateQuery = options.updateQuery !== false;

    activeFilter = filter;
    setButtonStates(filter);
    setCardVisibility(filter);
    syncVisibleVideoPlayback();

    if (shouldPersist) {
      persistFilter(filter);
    }

    if (shouldUpdateQuery) {
      setFilterQuery(filter);
    }
  }

  function onFilterClick(event) {
    const button = event.currentTarget;
    applyFilter(button.dataset.filter);
  }

  function bindFilterButtons() {
    getFilterButtons().forEach((button) => {
      button.addEventListener('click', onFilterClick);
    });
  }

  function initPublicationFilter() {
    if (!getFilterButtons().length) {
      return;
    }

    bindFilterButtons();

    const queryFilter = readFilterFromQuery();
    const initialFilter = queryFilter || loadSavedFilter() || DEFAULT_FILTER;

    applyFilter(initialFilter, { persist: true, updateQuery: true });
    resetVideoObserver();

    if (reducedMotionMedia) {
      const onMotionPreferenceChange = () => {
        resetVideoObserver();
        applyFilter(activeFilter, { persist: false, updateQuery: false });
      };

      if (typeof reducedMotionMedia.addEventListener === 'function') {
        reducedMotionMedia.addEventListener('change', onMotionPreferenceChange);
      } else if (typeof reducedMotionMedia.addListener === 'function') {
        reducedMotionMedia.addListener(onMotionPreferenceChange);
      }
    }
  }

  document.addEventListener('DOMContentLoaded', initPublicationFilter);
  window.showPublications = applyFilter;
})();
