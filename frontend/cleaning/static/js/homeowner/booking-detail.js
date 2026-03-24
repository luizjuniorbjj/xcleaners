/**
 * CleanClaw — Homeowner Booking Detail Module (Sprint 3)
 *
 * Booking detail with reschedule, cancel, and review options.
 */
window.HomeownerBookingDetail = {
  _booking: null,

  async render(container, params) {
    const bookingId = params?.id;
    if (!bookingId) {
      container.innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">No booking ID</div>
        </div>
      `;
      return;
    }

    // Skeleton loading
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <div class="cc-card" style="padding:var(--cc-space-6);">
          <div class="cc-skeleton cc-skeleton-text" style="width:40%;height:20px;"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:70%;margin-top:var(--cc-space-3);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:50%;margin-top:var(--cc-space-2);"></div>
        </div>
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-skeleton cc-skeleton-text" style="width:30%;height:16px;"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:80%;margin-top:var(--cc-space-3);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:60%;margin-top:var(--cc-space-2);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:45%;margin-top:var(--cc-space-2);"></div>
        </div>
      </div>
    `;

    try {
      const resp = await CleanAPI.cleanGet(`/my-bookings/${bookingId}`);
      this._booking = (resp && typeof resp === 'object' && resp.id) ? resp : null;
      if (!this._booking) {
        container.innerHTML = `
          <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '?'}</div>
            <div class="cc-empty-state-title">Booking not found</div>
            <button onclick="window.location.hash='#/homeowner/bookings'" class="cc-btn cc-btn-secondary" style="margin-top:var(--cc-space-4);">Back to Bookings</button>
          </div>
        `;
        return;
      }
      this._renderDetail(container);
    } catch (err) {
      console.error('[BookingDetail] Error:', err);
      container.innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">Could not load booking</div>
          <button onclick="window.location.hash='#/homeowner/bookings'" class="cc-btn cc-btn-secondary" style="margin-top:var(--cc-space-4);">Back</button>
        </div>
      `;
    }
  },

  _renderDetail(container) {
    const b = this._booking;
    const dateStr = new Date(b.scheduled_date + 'T00:00:00').toLocaleDateString('en-US', {
      weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    });

    const statusMap = {
      confirmed: 'cc-badge-success',
      pending: 'cc-badge-warning',
      completed: 'cc-badge-neutral',
      cancelled: 'cc-badge-danger',
      in_progress: 'cc-badge-info',
      scheduled: 'cc-badge-primary',
    };
    const badgeClass = statusMap[b.status] || 'cc-badge-neutral';

    container.innerHTML = `
      <div class="cc-booking-detail cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Back + Title -->
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
          <button class="cc-btn cc-btn-ghost cc-btn-sm" onclick="window.location.hash='#/homeowner/bookings'" style="padding:var(--cc-space-2);">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <h2 style="flex:1;margin:0;font-size:var(--cc-text-2xl);">Booking Detail</h2>
          <span class="cc-badge ${badgeClass}">${b.status}</span>
        </div>

        <!-- Hero: Date & Time -->
        <div class="cc-card" style="background:linear-gradient(135deg, var(--cc-primary-50), var(--cc-primary-100));padding:var(--cc-space-6);text-align:center;">
          <div class="cc-text-sm cc-text-muted" style="margin-bottom:var(--cc-space-2);text-transform:uppercase;letter-spacing:0.05em;">Scheduled</div>
          <div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);color:var(--cc-neutral-900);margin-bottom:var(--cc-space-1);">
            ${dateStr}
          </div>
          <div style="font-size:var(--cc-text-xl);color:var(--cc-primary-600);font-weight:var(--cc-font-semibold);">
            ${b.scheduled_start ? b.scheduled_start.substring(0, 5) : 'TBD'}${b.scheduled_end ? ' - ' + b.scheduled_end.substring(0, 5) : ''}
          </div>
        </div>

        <!-- Service Details -->
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">Service Details</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span class="cc-text-sm cc-text-muted">Service</span>
              <span class="cc-font-medium">${this._esc(b.service?.name || 'Cleaning')}</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span class="cc-text-sm cc-text-muted">Price</span>
              <span class="cc-font-bold" style="font-size:var(--cc-text-lg);color:var(--cc-neutral-900);">
                ${b.quoted_price ? '$' + b.quoted_price.toFixed(2) : 'TBD'}
              </span>
            </div>
          </div>
        </div>

        <!-- Team Info -->
        ${b.team_name ? `
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">Team</span>
          </div>
          <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
            <span class="cc-avatar cc-avatar-lg" style="font-size:var(--cc-text-lg);">
              ${this._esc(b.team_name).charAt(0)}
            </span>
            <div>
              <div class="cc-font-semibold" style="color:var(--cc-neutral-900);">${this._esc(b.team_name)}</div>
              <div class="cc-text-sm cc-text-muted">Assigned team</div>
            </div>
          </div>
        </div>
        ` : ''}

        <!-- Location -->
        ${b.address ? `
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">Location</span>
          </div>
          <div style="display:flex;align-items:flex-start;gap:var(--cc-space-3);">
            <div style="color:var(--cc-neutral-400);flex-shrink:0;margin-top:2px;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            </div>
            <span style="color:var(--cc-neutral-700);">${this._esc(b.address)}</span>
          </div>
        </div>
        ` : ''}

        <!-- Notes -->
        ${b.special_instructions ? `
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">Notes</span>
          </div>
          <p class="cc-text-sm" style="color:var(--cc-neutral-600);line-height:var(--cc-leading-relaxed);">${this._esc(b.special_instructions)}</p>
        </div>
        ` : ''}

        <!-- Booking Progress Timeline -->
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">Progress</span>
          </div>
          ${this._renderTimeline(b)}
        </div>

        <!-- Invoice -->
        ${b.invoice ? `
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">Invoice</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div class="cc-font-medium">${this._esc(b.invoice.number)}</div>
              <span class="cc-badge ${b.invoice.status === 'paid' ? 'cc-badge-success' : b.invoice.status === 'overdue' ? 'cc-badge-danger' : 'cc-badge-warning'}" style="margin-top:var(--cc-space-2);">${b.invoice.status}</span>
            </div>
            <span class="cc-font-bold" style="font-size:var(--cc-text-xl);color:var(--cc-neutral-900);">$${(b.invoice.total || 0).toFixed(2)}</span>
          </div>
        </div>
        ` : ''}

        <!-- Your Review -->
        ${b.review ? `
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">Your Review</span>
          </div>
          <div style="display:flex;gap:var(--cc-space-1);margin-bottom:var(--cc-space-2);">
            ${[1,2,3,4,5].map(n => `<span style="font-size:var(--cc-text-xl);color:${n <= b.review.rating ? 'var(--cc-warning-400)' : 'var(--cc-neutral-300)'};">${n <= b.review.rating ? '&#9733;' : '&#9734;'}</span>`).join('')}
          </div>
          ${b.review.comment ? `<p class="cc-text-sm" style="color:var(--cc-neutral-600);">${this._esc(b.review.comment)}</p>` : ''}
        </div>
        ` : ''}

        <!-- Actions -->
        <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);margin-top:var(--cc-space-2);">
          ${b.can_reschedule ? `
          <button class="cc-btn cc-btn-secondary cc-btn-lg cc-btn-block" id="cc-btn-reschedule">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
            Reschedule
          </button>
          ` : ''}
          ${b.can_cancel ? `
          <button class="cc-btn cc-btn-danger cc-btn-lg cc-btn-block" id="cc-btn-cancel">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>
            Cancel Booking
          </button>
          ` : ''}
          ${b.status === 'completed' && !b.review ? `
          <button class="cc-btn cc-btn-primary cc-btn-lg cc-btn-block" id="cc-btn-review">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            Leave a Review
          </button>
          ` : ''}
        </div>
      </div>
    `;

    // Attach listeners
    const reschedBtn = document.getElementById('cc-btn-reschedule');
    if (reschedBtn) reschedBtn.addEventListener('click', () => this._showRescheduleModal());

    const cancelBtn = document.getElementById('cc-btn-cancel');
    if (cancelBtn) cancelBtn.addEventListener('click', () => this._showCancelModal());

    const reviewBtn = document.getElementById('cc-btn-review');
    if (reviewBtn) reviewBtn.addEventListener('click', () => this._showReviewModal());
  },

  _showRescheduleModal() {
    const modal = document.createElement('div');
    modal.className = 'cc-modal-overlay';
    modal.innerHTML = `
      <div class="cc-modal">
        <h3>Reschedule Booking</h3>
        <div class="cc-form-group">
          <label>New Date</label>
          <input type="date" id="cc-resched-date" class="cc-input" min="${new Date().toISOString().split('T')[0]}">
        </div>
        <div class="cc-form-group">
          <label>Preferred Time (optional)</label>
          <input type="time" id="cc-resched-time" class="cc-input">
        </div>
        <div class="cc-modal-actions">
          <button class="cc-btn cc-btn-secondary" id="cc-resched-cancel">Cancel</button>
          <button class="cc-btn cc-btn-primary" id="cc-resched-confirm">Reschedule</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    document.getElementById('cc-resched-cancel').addEventListener('click', () => modal.remove());
    document.getElementById('cc-resched-confirm').addEventListener('click', async () => {
      const newDate = document.getElementById('cc-resched-date').value;
      const newTime = document.getElementById('cc-resched-time').value || null;
      if (!newDate) {
        CleanClaw.showToast('Please select a date.', 'warning');
        return;
      }
      try {
        const result = await CleanAPI.cleanPost(`/my-bookings/${this._booking.id}/reschedule`, {
          new_date: newDate,
          new_time: newTime,
        });
        if (result && result.success) {
          CleanClaw.showToast('Booking rescheduled. Your cleaning team has been notified.', 'success');
          modal.remove();
          this.render(document.querySelector('.cc-booking-detail')?.parentElement || document.getElementById('cc-main-content'), { id: this._booking.id });
        }
      } catch (err) {
        CleanClaw.showToast(err.detail || 'Could not reschedule. Please try again.', 'error');
      }
    });
  },

  _showCancelModal() {
    const modal = document.createElement('div');
    modal.className = 'cc-modal-overlay';
    modal.innerHTML = `
      <div class="cc-modal">
        <h3>Cancel Booking</h3>
        <p>Are you sure you want to cancel this cleaning?</p>
        <div class="cc-form-group">
          <label>Reason (optional)</label>
          <textarea id="cc-cancel-reason" class="cc-input" rows="2" placeholder="Why are you cancelling?"></textarea>
        </div>
        <div class="cc-modal-actions">
          <button class="cc-btn cc-btn-secondary" id="cc-cancel-no">Keep Booking</button>
          <button class="cc-btn cc-btn-danger" id="cc-cancel-yes">Cancel Booking</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    document.getElementById('cc-cancel-no').addEventListener('click', () => modal.remove());
    document.getElementById('cc-cancel-yes').addEventListener('click', async () => {
      const reason = document.getElementById('cc-cancel-reason').value.trim() || null;
      try {
        const result = await CleanAPI.cleanPost(`/my-bookings/${this._booking.id}/cancel`, { reason });
        if (result && result.success) {
          CleanClaw.showToast('Booking cancelled. Your cleaning team has been notified.', 'success');
          modal.remove();
          window.location.hash = '#/homeowner/bookings';
        }
      } catch (err) {
        CleanClaw.showToast(err.detail || 'Could not cancel booking. Please try again.', 'error');
      }
    });
  },

  _showReviewModal() {
    let selectedRating = 0;
    const modal = document.createElement('div');
    modal.className = 'cc-modal-overlay';
    modal.innerHTML = `
      <div class="cc-modal">
        <h3>Rate Your Cleaning</h3>
        <div class="cc-star-rating" id="cc-star-rating">
          ${[1,2,3,4,5].map(n => `<button class="cc-star" data-rating="${n}">&#9734;</button>`).join('')}
        </div>
        <div class="cc-form-group">
          <label>Comments (optional)</label>
          <textarea id="cc-review-comment" class="cc-input" rows="3" placeholder="How was the service?"></textarea>
        </div>
        <div class="cc-modal-actions">
          <button class="cc-btn cc-btn-secondary" id="cc-review-cancel">Cancel</button>
          <button class="cc-btn cc-btn-primary" id="cc-review-submit">Submit Review</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    modal.querySelectorAll('.cc-star').forEach(star => {
      star.addEventListener('click', () => {
        selectedRating = parseInt(star.dataset.rating);
        modal.querySelectorAll('.cc-star').forEach((s, i) => {
          s.innerHTML = i < selectedRating ? '&#9733;' : '&#9734;';
          s.classList.toggle('cc-star-active', i < selectedRating);
        });
      });
    });

    document.getElementById('cc-review-cancel').addEventListener('click', () => modal.remove());
    document.getElementById('cc-review-submit').addEventListener('click', async () => {
      if (selectedRating === 0) {
        CleanClaw.showToast('Please select a rating.', 'warning');
        return;
      }
      const comment = document.getElementById('cc-review-comment').value.trim() || null;
      try {
        const result = await CleanAPI.cleanPost(`/my-bookings/${this._booking.id}/review`, {
          rating: selectedRating,
          comment,
        });
        if (result && result.success) {
          CleanClaw.showToast('Thank you for your feedback! Your review helps us improve.', 'success');
          modal.remove();
          this.render(document.querySelector('.cc-booking-detail')?.parentElement || document.getElementById('cc-main-content'), { id: this._booking.id });
        }
      } catch (err) {
        CleanClaw.showToast(err.detail || 'Could not submit review. Please try again.', 'error');
      }
    });
  },

  _renderTimeline(b) {
    // Define the progression steps
    const steps = [
      { key: 'created', label: 'Created', timestamp: b.created_at },
      { key: 'confirmed', label: 'Confirmed', timestamp: b.confirmed_at },
      { key: 'team_assigned', label: 'Team Assigned', timestamp: b.team_assigned_at || (b.team_name ? (b.confirmed_at || b.created_at) : null) },
      { key: 'in_progress', label: 'In Progress', timestamp: b.actual_start },
      { key: 'completed', label: 'Completed', timestamp: b.actual_end || (b.status === 'completed' ? (b.completed_at || b.actual_start) : null) },
    ];

    // Determine current step index based on status
    const statusToStep = {
      'pending': 0,
      'confirmed': 1,
      'scheduled': 2,
      'in_progress': 3,
      'completed': 4,
      'cancelled': -1,
    };
    const currentIdx = statusToStep[b.status] ?? 0;

    if (b.status === 'cancelled') {
      return `
        <div style="text-align:center;padding:var(--cc-space-4);">
          <span class="cc-badge cc-badge-danger" style="font-size:var(--cc-text-sm);">Booking Cancelled</span>
          ${b.cancelled_at ? `<div class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-2);">${new Date(b.cancelled_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} at ${new Date(b.cancelled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>` : ''}
        </div>
      `;
    }

    // Horizontal progress bar
    const pct = Math.round((currentIdx / (steps.length - 1)) * 100);
    let html = `
      <div style="position:relative;margin-bottom:var(--cc-space-5);">
        <div style="height:4px;background:var(--cc-neutral-200);border-radius:var(--cc-radius-full);overflow:hidden;">
          <div style="height:100%;width:${pct}%;background:var(--cc-primary-500);border-radius:var(--cc-radius-full);transition:width 0.5s ease;"></div>
        </div>
      </div>
    `;

    // Steps
    html += '<div style="display:flex;justify-content:space-between;gap:var(--cc-space-1);">';
    steps.forEach((step, i) => {
      const isDone = i <= currentIdx;
      const isCurrent = i === currentIdx;
      const dotColor = isDone ? 'var(--cc-primary-500)' : 'var(--cc-neutral-300)';
      const dotSize = isCurrent ? '14px' : '10px';
      const ring = isCurrent ? 'box-shadow:0 0 0 3px var(--cc-primary-100);' : '';
      const labelWeight = isCurrent ? 'font-weight:var(--cc-font-semibold);color:var(--cc-primary-600);' : isDone ? 'color:var(--cc-neutral-700);' : 'color:var(--cc-neutral-400);';
      const ts = isDone && step.timestamp
        ? new Date(step.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        : '';

      html += `
        <div style="display:flex;flex-direction:column;align-items:center;flex:1;min-width:0;">
          <div style="width:${dotSize};height:${dotSize};border-radius:50%;background:${dotColor};${ring}margin-bottom:var(--cc-space-2);transition:all 0.3s ease;"></div>
          <span class="cc-text-xs" style="${labelWeight}text-align:center;line-height:1.3;">${step.label}</span>
          ${ts ? `<span class="cc-text-xs cc-text-muted" style="margin-top:2px;">${ts}</span>` : ''}
        </div>
      `;
    });
    html += '</div>';

    return html;
  },

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};
