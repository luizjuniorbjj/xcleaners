/**
 * CleanClaw — Offline Store (Sprint 3)
 *
 * IndexedDB wrapper for offline support (cleaner role).
 * Stores: today's jobs, checklists, queued actions for sync.
 *
 * Usage:
 *   OfflineStore.saveForOffline(jobs);
 *   OfflineStore.queueAction({ type: 'checkin', bookingId, lat, lng });
 *   await OfflineStore.syncPending();
 *   const count = await OfflineStore.getPendingCount();
 */
window.OfflineStore = {
  _DB_NAME: 'cleanclaw-offline',
  _DB_VERSION: 1,
  _db: null,

  // Store names
  STORE_JOBS: 'today_jobs',
  STORE_QUEUE: 'action_queue',

  /**
   * Open/create the IndexedDB database.
   */
  async _getDb() {
    if (this._db) return this._db;

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this._DB_NAME, this._DB_VERSION);

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // Today's jobs store
        if (!db.objectStoreNames.contains(this.STORE_JOBS)) {
          db.createObjectStore(this.STORE_JOBS, { keyPath: 'id' });
        }

        // Action queue store (auto-increment key)
        if (!db.objectStoreNames.contains(this.STORE_QUEUE)) {
          const queueStore = db.createObjectStore(this.STORE_QUEUE, {
            keyPath: 'queueId',
            autoIncrement: true,
          });
          queueStore.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };

      request.onsuccess = (event) => {
        this._db = event.target.result;
        resolve(this._db);
      };

      request.onerror = (event) => {
        console.error('[OfflineStore] IndexedDB open error:', event.target.error);
        reject(event.target.error);
      };
    });
  },

  /**
   * Save today's jobs for offline access.
   * Replaces all existing cached jobs.
   */
  async saveForOffline(jobs) {
    try {
      const db = await this._getDb();
      const tx = db.transaction(this.STORE_JOBS, 'readwrite');
      const store = tx.objectStore(this.STORE_JOBS);

      // Clear existing
      store.clear();

      // Add new jobs
      for (const job of jobs) {
        store.put({ ...job, _cachedAt: Date.now() });
      }

      await new Promise((resolve, reject) => {
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
      });

      console.log(`[OfflineStore] Cached ${jobs.length} jobs for offline`);
    } catch (err) {
      console.warn('[OfflineStore] Failed to cache jobs:', err);
    }
  },

  /**
   * Get cached jobs (used when offline).
   */
  async getCachedJobs() {
    try {
      const db = await this._getDb();
      const tx = db.transaction(this.STORE_JOBS, 'readonly');
      const store = tx.objectStore(this.STORE_JOBS);

      return new Promise((resolve, reject) => {
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result || []);
        request.onerror = () => reject(request.error);
      });
    } catch (err) {
      console.warn('[OfflineStore] Failed to get cached jobs:', err);
      return [];
    }
  },

  /**
   * Queue an action for later sync (check-in, check-out, notes, etc.).
   * Actions are stored in IndexedDB and sent when back online.
   */
  async queueAction(action) {
    try {
      const db = await this._getDb();
      const tx = db.transaction(this.STORE_QUEUE, 'readwrite');
      const store = tx.objectStore(this.STORE_QUEUE);

      store.add({
        ...action,
        timestamp: Date.now(),
        synced: false,
      });

      await new Promise((resolve, reject) => {
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
      });

      console.log(`[OfflineStore] Queued action: ${action.type}`);
      this._updateBadge();
    } catch (err) {
      console.warn('[OfflineStore] Failed to queue action:', err);
    }
  },

  /**
   * Sync all pending queued actions.
   * Called when the device comes back online.
   */
  async syncPending() {
    try {
      const db = await this._getDb();
      const tx = db.transaction(this.STORE_QUEUE, 'readonly');
      const store = tx.objectStore(this.STORE_QUEUE);

      const allActions = await new Promise((resolve, reject) => {
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result || []);
        request.onerror = () => reject(request.error);
      });

      if (allActions.length === 0) return;

      console.log(`[OfflineStore] Syncing ${allActions.length} queued actions`);
      let synced = 0;
      let failed = 0;

      for (const action of allActions) {
        try {
          await this._executeAction(action);
          // Remove from queue
          const delTx = db.transaction(this.STORE_QUEUE, 'readwrite');
          delTx.objectStore(this.STORE_QUEUE).delete(action.queueId);
          await new Promise((resolve) => { delTx.oncomplete = resolve; });
          synced++;
        } catch (err) {
          console.warn(`[OfflineStore] Failed to sync action ${action.type}:`, err);
          failed++;
        }
      }

      if (synced > 0 && typeof CleanClaw !== 'undefined' && CleanClaw.showToast) {
        CleanClaw.showToast(`${synced} queued action(s) synced.`, 'success');
      }
      if (failed > 0 && typeof CleanClaw !== 'undefined' && CleanClaw.showToast) {
        CleanClaw.showToast(`${failed} action(s) failed to sync. Will retry later.`, 'warning');
      }

      this._updateBadge();
    } catch (err) {
      console.warn('[OfflineStore] Sync error:', err);
    }
  },

  /**
   * Execute a single queued action against the API.
   */
  async _executeAction(action) {
    switch (action.type) {
      case 'checkin':
        await CleanAPI.cleanPost(`/my-jobs/${action.bookingId}/checkin`, {
          lat: action.lat, lng: action.lng,
        });
        break;

      case 'checkout':
        await CleanAPI.cleanPost(`/my-jobs/${action.bookingId}/checkout`, {
          lat: action.lat, lng: action.lng, notes: action.notes,
        });
        break;

      case 'note':
        await CleanAPI.cleanPost(`/my-jobs/${action.bookingId}/note`, {
          note: action.note, photo_url: action.photoUrl,
        });
        break;

      case 'checklist_complete':
        await CleanAPI.cleanPost(
          `/my-jobs/${action.bookingId}/checklist/${action.itemId}/complete`, {}
        );
        break;

      case 'issue':
        await CleanAPI.cleanPost(`/my-jobs/${action.bookingId}/issue`, {
          issue_type: action.issueType, description: action.description,
        });
        break;

      default:
        console.warn(`[OfflineStore] Unknown action type: ${action.type}`);
    }
  },

  /**
   * Get count of pending (unsynced) actions.
   */
  async getPendingCount() {
    try {
      const db = await this._getDb();
      const tx = db.transaction(this.STORE_QUEUE, 'readonly');
      const store = tx.objectStore(this.STORE_QUEUE);

      return new Promise((resolve, reject) => {
        const request = store.count();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    } catch (err) {
      return 0;
    }
  },

  /**
   * Update the sync badge in the UI (if element exists).
   */
  async _updateBadge() {
    const count = await this.getPendingCount();
    const badge = document.getElementById('cc-sync-badge');
    if (badge) {
      if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'inline-flex';
      } else {
        badge.style.display = 'none';
      }
    }
  },

  /**
   * Initialize: set up online/offline listeners for auto-sync.
   */
  init() {
    window.addEventListener('online', () => {
      console.log('[OfflineStore] Back online, syncing...');
      this.syncPending();
    });

    // Update badge on load
    this._updateBadge();
  },
};

// Auto-initialize
if (typeof window !== 'undefined') {
  OfflineStore.init();
}
