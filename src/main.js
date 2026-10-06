import './style.css';
import { Html5Qrcode } from 'html5-qrcode';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';
const AUTH_KEY = 'codex_cybersquad_auth';
// Must match the courses.thumbnail database column width (db.String(500)).
const THUMBNAIL_MAX_LENGTH = 500;

let authState = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null');
const inFlightGets = new Map();

// Friendlier, actionable copy for known 409 (conflict) error codes returned by the API.
const CONFLICT_MESSAGES = {
  ENROLLMENT_EXISTS: 'You already own this course. Open "My Courses" to start learning.',
  ALREADY_INSTRUCTOR: 'You already have instructor access. Open your instructor workspace to manage courses.',
  APPLICATION_ALREADY_PENDING: 'Your instructor application is still awaiting review. The academy will contact you with the next step.',
  APPLICATION_ALREADY_APPROVED: 'This instructor application has already been approved.',
  COURSE_DELETE_DENIED: 'Only draft or rejected courses can be deleted. Published or pending courses must stay available to students.',
  COURSE_SUBMIT_DENIED: 'This course has already been submitted. Only draft or rejected courses can be submitted for review.',
  COURSE_NOT_PENDING: 'Only courses that are awaiting review can be approved or rejected.',
  MODULE_ORDER_EXISTS: 'Another module in this course already uses that order number. Choose a different one.',
  LESSON_ORDER_EXISTS: 'Another lesson in this module already uses that order number. Choose a different one.',
  EMAIL_ALREADY_EXISTS: 'That email is already registered. Try logging in instead.'
};

// Tracks the most recent 409 so toasts raised from catch blocks (which only receive
// error.message) can render conflict errors with the right tone and follow-up action.
let lastApiConflict = null;
const api = {
  async request(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (authState?.access_token) headers.Authorization = `Bearer ${authState.access_token}`;
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } catch (error) {
      throw new Error('Unable to connect to the server.');
    }
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      clearAuthSession();
      window.location.hash = '#login';
    }
    if (!response.ok || payload.success === false) {
      const fieldErrors = payload.details || payload.errors;
      const details = fieldErrors && typeof fieldErrors === 'object'
        ? Object.values(fieldErrors).filter(Boolean).join(' ')
        : '';
      const code = typeof payload.error === 'string' ? payload.error : '';
      let message = [payload.message, details].filter(Boolean).join(' — ') || payload.error || `Request failed (${response.status}).`;
      if (response.status === 409 && CONFLICT_MESSAGES[code]) message = CONFLICT_MESSAGES[code];
      if (response.status === 409) lastApiConflict = { code, message };
      const failure = new Error(message);
      failure.status = response.status;
      failure.code = code;
      throw failure;
    }
    return payload.data || {};
  },
  get(path) {
    if (inFlightGets.has(path)) return inFlightGets.get(path);
    const request = this.request(path).finally(() => inFlightGets.delete(path));
    inFlightGets.set(path, request);
    return request;
  },
  post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body) }); },
  put(path, body) { return this.request(path, { method: 'PUT', body: JSON.stringify(body) }); },
  patch(path, body) { return this.request(path, { method: 'PATCH', body: JSON.stringify(body) }); },
  delete(path) { return this.request(path, { method: 'DELETE' }); }
};

const fmt = n => `₦${n.toLocaleString('en-NG')}`;
function fmtDate(value) { if (!value) return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric' }); }
function paymentMeta(payment) { const when = fmtDate(payment.paid_at || payment.created_at); return `${escapeHtml(payment.status)} · ${fmt(payment.amount)}${when ? ` · ${when}` : ''}`; }
const initialState = () => ({ page: 'home', query: '', category: 'All', categoryId: null, filters: { language: '', level: '', price: '' }, toast: '', courses: [], categories: [], loading: false, error: '' });
let state = initialState();
let coursesStale = true;
let categoriesLoaded = false;
function routeFromHash() { return decodeURIComponent(window.location.hash.slice(1) || 'home'); }
function currentRole() { return authState?.user?.role || null; }
function homeRouteForRole() {
  const role = currentRole();
  if (role === 'admin') return 'admin';
  if (role === 'instructor') return 'instructor';
  if (role === 'student') return 'dashboard';
  return 'login';
}
function navItemsForRole(role) {
  if (role === 'admin') {
    return [
      ['admin', '▣', 'Admin Console'],
      ['codex-ids', '🆔', 'Codex IDs'],
      ['all-sessions', '📋', 'All Sessions'],
      ['catalog', '▦', 'Browse Courses'],
    ];
  }
  if (role === 'instructor') {
    return [
      ['instructor', '✦', 'Instructor Workspace'],
      ['attendance-sessions', '📋', 'Attendance Sessions'],
      ['qr-scanner', '📷', 'QR Scanner'],
      ['catalog', '▦', 'Browse Courses'],
    ];
  }
  if (role === 'student') {
    return [
      ['dashboard', '◫', 'Student Dashboard'],
      ['catalog', '▦', 'Browse Courses'],
      ['my-courses', '▣', 'My Courses'],
      ['progress', '◷', 'Progress'],
      ['codex-id', '🆔', 'Codex ID'],
      ['attendance', '📋', 'Attendance'],
      ['payments', '₦', 'Payment History'],
      ['instructor', '✦', 'Become an Instructor'],
    ];
  }
  return [
    ['home', '⌂', 'Home'],
    ['catalog', '▦', 'Browse Courses'],
  ];
}
function canVisit(route) {
  const role = currentRole();
  const base = route.includes(':') ? route.split(':')[0] : route;
  const publicRoutes = new Set(['home', 'login', 'register', 'catalog', 'course']);
  if (publicRoutes.has(route) || publicRoutes.has(base)) return true;
  if (!authState) return false;
  if (route === 'admin') return role === 'admin';
  if (route === 'instructor') return role === 'student' || role === 'instructor';
  if (base === 'edit-course') return role === 'instructor';
  if (['attendance-sessions', 'qr-scanner'].includes(route)) return role === 'instructor' || role === 'admin';
  if (['codex-ids', 'all-sessions'].includes(route)) return role === 'admin';
  if (['dashboard', 'my-courses', 'progress', 'payments', 'codex-id', 'attendance'].includes(route) || base === 'learn' || base === 'checkout') {
    return role === 'student';
  }
  return true;
}
function hydrateForRoute(route) {
  if (route === 'admin') refreshAdmin();
  else if (route.startsWith('edit-course:')) refreshCourseEditor(route.split(':')[1]);
  else window.__hydratePage?.();
}
function navigate(route) {
  if (!canVisit(route)) {
    toast(authState ? 'You do not have permission to view that area.' : 'Please log in to continue.');
    route = authState ? homeRouteForRole() : 'login';
  }
  if (route === 'my-courses') state.category = 'All';
  const hash = `#${route}`;
  if (window.location.hash !== hash && decodeURIComponent(window.location.hash.slice(1) || '') !== route) {
    state.page = route;
    window.location.hash = route;
    return;
  }
  state.page = route;
  render();
  hydrateForRoute(route);
}
function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function extractYouTubeId(url) {
  if (!url) return null;
  try {
    const parsed = new URL(String(url).trim());
    if (!/^https?:$/i.test(parsed.protocol)) return null;
    const host = parsed.hostname.replace(/^www\./i, '').toLowerCase();
    if (host === 'youtu.be') {
      const id = parsed.pathname.split('/').filter(Boolean)[0] || '';
      return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null;
    }
    if (host === 'youtube.com' || host === 'm.youtube.com') {
      if (parsed.pathname.startsWith('/embed/') || parsed.pathname.startsWith('/shorts/')) {
        const id = parsed.pathname.split('/').filter(Boolean)[1] || '';
        return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null;
      }
      const id = parsed.searchParams.get('v') || '';
      return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null;
    }
  } catch (_) { /* ignore invalid URLs */ }
  return null;
}
function resourcesBlock(lesson) {
  const items = (Array.isArray(lesson?.resources) ? lesson.resources : []).filter(resource => resource && resource.file_url);
  if (!items.length) return '';
  return `<div class="lesson-resources"><div class="eyebrow green-text">LESSON RESOURCES</div>${items.map(resource => `<a href="${escapeHtml(resource.file_url)}" target="_blank" rel="noopener noreferrer">${icon('certificate')} ${escapeHtml(resource.name)} <small>${escapeHtml(resource.file_type || 'file')}</small></a>`).join('')}</div>`;
}
function renderLessonVideo(videoUrl) {
  const safeUrl = String(videoUrl || '').trim();
  if (!safeUrl) return '';
  const youtubeId = extractYouTubeId(safeUrl);
  if (youtubeId) {
    return `<div class="lesson-video-embed"><iframe src="https://www.youtube.com/embed/${youtubeId}" title="Lesson video" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div>`;
  }
  if (/^https:\/\//i.test(safeUrl) && !/^(javascript|data):/i.test(safeUrl)) {
    return `<video class="lesson-video" controls src="${escapeHtml(safeUrl)}"></video>`;
  }
  return `<p class="muted">This lesson video URL is not a supported YouTube or HTTPS media link.</p>`;
}
function apiCourse(course) {
  return { ...course, id: String(course.id), category: course.category?.name || course.category || '', instructor: course.instructor?.full_name || course.instructor || '', lang: course.language || '', level: course.level || '', rating: course.rating?.average ?? '', students: course.enrolled_count ?? '', duration: course.duration == null ? '' : `${Math.floor(course.duration / 60)}h ${course.duration % 60}m`, price: Number(course.price || 0), icon: '✦', color: 'mint', progress: 0 };
}
function catalogCourses() { return state.courses; }
function loading(message = 'Loading your learning space...') { return `<div class="live-state"><span class="loader"></span><p>${message}</p></div>`; }
function errorState(message, route) { return `<div class="live-state error-state"><h3>Unable to load this page</h3><p>${escapeHtml(message)}</p><button class="btn btn-outline" data-action="retry" data-retry="${route}">Try again</button></div>`; }
async function loadCourses() {
  try {
    const data = await api.get('/courses');
    function liveCourse(course) { return apiCourse(course); }
    function liveDashboard(data) {
      const stats = data.statistics || {};
      const items = data.continue_learning || [];
      return `<div class="dashboard-head"><div><div class="eyebrow green-text">${new Date().toLocaleDateString('en-NG',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</div><h1>Welcome back, ${escapeHtml(data.student?.full_name || authState?.user?.full_name || 'learner')}</h1><p class="muted">Create an account and start learning at your own pace.</p></div><div class="dashboard-actions">${button('Browse courses','catalog','btn btn-outline')}</div></div><div class="metric-grid"><div class="metric-card"><strong>${stats.enrolled_courses || 0}</strong><small>Enrolled courses</small></div><div class="metric-card"><strong>${stats.active_courses || 0}</strong><small>Active courses</small></div><div class="metric-card"><strong>${stats.completed_courses || 0}</strong><small>Completed courses</small></div><div class="metric-card"><strong>${stats.overall_learning_progress || 0}%</strong><small>Overall progress</small></div></div><div class="section-heading compact-heading"><h2>Continue learning</h2><a data-route="my-courses" class="text-link">View all ${icon('arrow')}</a></div>${items.length?`<div class="learning-list">${items.map(item=>{const c=liveCourse(item.course||{});return `<article class="learning-item"><div class="tiny-art mint">✦</div><div class="learning-info"><div class="eyebrow">${escapeHtml(c.category)}</div><h3>${escapeHtml(c.title)}</h3><div class="progress-line"><span style="width:${item.progress_percentage||0}%"></span></div><small>${item.progress_percentage||0}% complete</small></div><button class="play-btn" data-route="learn:${c.id}">${icon('play')}</button></article>`}).join('')}</div>`:'<div class="empty-state"><h3>No enrolled courses yet.</h3><p class="muted">Explore the catalog and start your first course.</p></div>'}`;
    }
    function liveMyCourses(data) { const items=data.courses||[]; return `<div class="page-intro"><div><div class="eyebrow green-text">YOUR LEARNING</div><h1>My courses</h1><p class="muted">Your enrolled courses and progress.</p></div>${button('Explore courses','catalog','btn btn-outline')}</div>${items.length?`<div class="course-grid">${items.map(item=>{const c=liveCourse(item.course||{});return courseCard({...c,progress:item.progress_percentage||0})}).join('')}</div>`:'<div class="empty-state"><h3>No enrolled courses yet.</h3><p class="muted">Your purchased and free courses will appear here.</p></div>'}`; }
    async function hydratePage() {
      const route=state.page;
      if (!authState && ['dashboard','my-courses','progress','payments','instructor','admin','codex-id','attendance','attendance-sessions','qr-scanner','codex-ids','all-sessions'].includes(route)) return;
      if (route==='home' || route==='catalog') {
        if (coursesStale || !state.courses.length || !categoriesLoaded) {
          try { await Promise.all([loadCourses(), loadCategories()]); } catch (_) { /* surfaced via state.error */ }
          render();
        }
        return;
      }
      const target=document.querySelector('.app-content') || document.querySelector('.detail-page') || document.querySelector('.checkout-page');
      if (!target) return;
      if (route==='dashboard' || route==='my-courses') {
        target.innerHTML=loading();
        try { const data=route==='dashboard'?await api.get('/student/dashboard'):await api.get('/my-courses'); const payments=route==='dashboard'?await api.get('/student/payments'):null; target.innerHTML=route==='dashboard'?`${liveDashboard(data)}<section class="panel payment-history"><h2>Recent payments</h2>${payments?.payments?.length?payments.payments.slice(0,5).map(payment=>`<div class="pending-row"><strong>${escapeHtml(payment.course?.title||payment.reference)}</strong><span>${paymentMeta(payment)}</span></div>`).join(''):'<div class="empty-state">No payment history.</div>'}`:liveMyCourses(data); bind(); }
        catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route.startsWith('course:')) {
        const id=route.split(':')[1]; const detailTarget=document.querySelector('.detail-page');
        try { const data=await api.get(`/courses/${Number(id)}`); const lessons=await api.get(`/courses/${Number(id)}/lessons`); const c=liveCourse(data.course); const modules=(lessons.modules||[]).map(module=>`<div class="module"><span>${String(module.order||1).padStart(2,'0')}</span><strong>${escapeHtml(module.title)}</strong><small>${(module.lessons||[]).length} lessons</small><b>⌄</b></div>`).join(''); detailTarget.outerHTML=courseDetailLive(c,modules); bind(); }
        catch(error) { detailTarget.innerHTML=errorState(error.message,route); bind(); }
      } else if (route.startsWith('learn:')) {
        const id=route.split(':')[1]; const learnTarget=document.querySelector('.learn-layout');
        try { const data=await api.get(`/my-courses/${Number(id)}/learning`); learnTarget.outerHTML=learningLive(data); bind(); }
        catch(error) { learnTarget.outerHTML=errorState(error.message,route); bind(); }
      } else if (route.startsWith('checkout:')) {
        const id=route.split(':')[1]; const target=document.querySelector('.checkout-page');
        try { const data=await api.get(`/courses/${Number(id)}`); const c=liveCourse(data.course); target.outerHTML=checkoutLive(c); bind(); }
        catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='payments') {
        target.innerHTML=loading('Loading payment history...');
        try {
          const payments=await api.get('/student/payments');
          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">PAYMENTS</div><h1>Payment history</h1><p class="muted">Your academy payment records.</p></div>${button('Browse courses','catalog','btn btn-outline')}</div><section class="panel payment-history">${payments?.payments?.length?payments.payments.map(payment=>`<div class="pending-row"><strong>${escapeHtml(payment.course?.title||payment.reference)}</strong><span>${paymentMeta(payment)}</span></div>`).join(''):'<div class="empty-state">No payment history.</div>'}</section>`;
          bind();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='progress') {
        target.innerHTML=loading('Loading your progress...');
        try {
          const data=await api.get('/my-courses');
          const items=data.courses||[];
          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">YOUR PROGRESS</div><h1>Learning progress</h1><p class="muted">Track completion across your enrolled courses.</p></div>${button('My courses','my-courses','btn btn-outline')}</div>${items.length?`<div class="learning-list">${items.map(item=>{const c=apiCourse(item.course||{});const pct=item.progress_percentage||0;return `<article class="learning-item"><div class="tiny-art mint">✦</div><div class="learning-info"><div class="eyebrow">${escapeHtml(c.category)}</div><h3>${escapeHtml(c.title)}</h3><div class="progress-line"><span style="width:${pct}%"></span></div><small>${pct}% complete</small></div><button class="play-btn" data-route="learn:${c.id}">${icon('play')}</button></article>`}).join('')}</div>`:'<div class="empty-state"><h3>No progress yet.</h3><p class="muted">Enroll in a course to start tracking progress.</p></div>'}`;
          bind();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='codex-id') {
        target.innerHTML=loading('Loading your Codex ID...');
        try {
          const data=await api.get('/student/codex-id');
          const codex=data.codex_id||{};
          const user=codex.user||{};
          const enrollment=codex.enrollment||{};
          const profileImage=user.profile_image;
          const photoHtml=profileImage?`<img class="id-card-photo" src="${escapeHtml(profileImage)}" alt="${escapeHtml(user.full_name||'Student')}" onerror="this.style.display='none'">`:`<div class="id-card-photo-placeholder">${(user.full_name||'CS').slice(0,2).toUpperCase()}</div>`;
          const courseTitle=enrollment.course_title||'Student';
          const enrollmentDate=enrollment.enrolled_at?fmtDate(enrollment.enrolled_at):'Not enrolled';
          const statusClass=codex.status==='active'?'status-active':codex.status==='suspended'?'status-suspended':'status-revoked';

          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">CODEX STUDENT ID</div><h1>Your Digital Identity</h1><p class="muted">Your official Codex Academy student identification card.</p></div></div>${codex.codex_id?`<div class="id-card-container"><button class="id-card-toggle" data-action="flip-card">Flip Card</button><div class="id-card"><div class="id-card-front" id="id-card-front"><div class="id-card-top-section"><div class="id-card-branding"><div class="id-card-logo">CODEX</div><div class="id-card-brand-line"></div></div><div class="id-card-title">STUDENT ID CARD</div></div><div class="id-card-content"><div class="id-card-photo-section">${photoHtml}</div><div class="id-card-info"><div class="id-card-name">${escapeHtml(user.full_name||'Unknown')}</div><div class="id-card-id">${escapeHtml(codex.codex_id)}</div><div class="id-card-status-badge ${statusClass}">${escapeHtml(codex.status.toUpperCase())}</div></div></div></div><div class="id-card-bottom-section"><div class="id-card-academic-info"><div class="id-card-academic-label">CURRENT COURSE</div><div class="id-card-academic-value">${escapeHtml(courseTitle)}</div><div class="id-card-academic-label">ENROLLED</div><div class="id-card-academic-value">${enrollmentDate}</div></div><div class="id-card-qr-section"><div class="id-card-qr" id="qr-code-display"></div><div class="id-card-qr-label">VERIFY</div></div></div></div></div>`:'<div class="empty-state"><h3>No Codex ID issued</h3><p class="muted">Contact administration to request your student ID card.</p></div>'}`;
          if (codex.qr_token && typeof QRCode !== 'undefined') {
            QRCode.toCanvas(document.getElementById('qr-code-display'), codex.qr_token, { width: 75, margin: 1 });
          }
          bind();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='attendance') {
        target.innerHTML=loading('Loading attendance history...');
        try {
          const data=await api.get('/student/attendance');
          const records=data.attendance||[];
          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">ATTENDANCE HISTORY</div><h1>Event Attendance</h1><p class="muted">Your recorded attendance at academy events and workshops.</p></div></div>${records.length?`<div class="panel attendance-list">${records.map(record=>`<div class="attendance-row"><div><strong>${escapeHtml(record.session?.title||'Event')}</strong><small>${escapeHtml(record.session?.session_type||'Event')} · ${fmtDate(record.scanned_at)}</small></div><div class="attendance-status ${record.status}">${escapeHtml(record.status)}</div></div>`).join('')}</div>`:'<div class="empty-state"><h3>No attendance records</h3><p class="muted">Your event attendance will appear here after scanning your Codex ID.</p></div>'}`;
          bind();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='attendance-sessions') {
        target.innerHTML=loading('Loading attendance sessions...');
        try {
          const data=await api.get('/instructor/attendance/sessions');
          const sessions=data.sessions||[];
          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">ATTENDANCE SESSIONS</div><h1>Event Sessions</h1><p class="muted">Create and manage attendance tracking sessions for events and workshops.</p></div><button class="btn btn-primary" data-action="show-session-form">Create session ${icon('arrow')}</button></div><div id="session-form"></div>${sessions.length?`<div class="panel attendance-list">${sessions.map(session=>`<div class="attendance-row"><div><strong>${escapeHtml(session.title)}</strong><small>${escapeHtml(session.session_type)} · ${fmtDate(session.starts_at)} · ${session.records_count||0} records</small></div><div class="session-status ${session.status}">${escapeHtml(session.status)}</div><div class="action-row">${actionButton(session.status==='draft'?'Activate':session.status==='active'?'Close':'View',session.status==='draft'?'activate-session':session.status==='active'?'close-session':'view-session',session.id)}</div></div>`).join('')}</div>`:'<div class="empty-state"><h3>No sessions created</h3><p class="muted">Create a session to start tracking attendance.</p></div>'}`;
          bind();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='qr-scanner') {
        target.innerHTML=loading('Loading scanner...');
        try {
          const role = currentRole();
          const sessionsEndpoint = role === 'admin' ? '/admin/attendance/sessions' : '/instructor/attendance/sessions';
          const sessionsData = await api.get(sessionsEndpoint);
          const sessions = sessionsData.sessions || [];
          const activeSessions = sessions.filter(s => s.status === 'active');
          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">QR SCANNER</div><h1>Scan Student IDs</h1><p class="muted">Scan student QR codes to verify identity or record attendance for active sessions.</p></div></div><div class="scanner-layout"><div class="scanner-panel"><div id="qr-reader"></div><div class="scanner-controls"><select id="session-select" class="form-select"><option value="">Select session for attendance recording</option>${activeSessions.map(s=>`<option value="${s.id}">${escapeHtml(s.title)} (${escapeHtml(s.session_type)})</option>`).join('')}</select><div class="scanner-mode"><label><input type="radio" name="scan-mode" value="verify" checked> Verify only</label><label><input type="radio" name="scan-mode" value="record"> Record attendance</label></div><button class="btn btn-small btn-outline" id="start-scanner">Start Camera</button><button class="btn btn-small btn-outline" id="stop-scanner" style="display:none">Stop Camera</button></div></div><div class="scan-results" id="scan-results"></div></div>`;
          bind();
          initQrScanner();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='instructor') {
        const target=document.querySelector('.app-content'); target.innerHTML=loading('Loading your instructor workspace...');
        try {
          if (authState.user?.role === 'instructor') {
            const data=await api.get('/instructor/courses');
            const application=await api.get('/instructor/application').catch(()=>({application:null}));
            target.innerHTML=`${instructorWorkspace(data)}<div class="panel application-status"><h3>Application status</h3><p class="muted">${escapeHtml(application.application?.status||'Approved instructor')}</p></div>`;
          } else {
            const application=await api.get('/instructor/application').catch(()=>({application:null}));
            target.innerHTML=instructorApplication(application.application);
          }
          bind();
        }
        catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='codex-ids') {
        target.innerHTML=loading('Loading Codex IDs...');
        try {
          const data=await api.get('/admin/codex-ids');
          const codexIds=data.codex_ids||[];
          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">CODEX STUDENT IDS</div><h1>Student IDs</h1><p class="muted">Manage all student Codex IDs and their status.</p></div><button class="btn btn-primary" data-action="show-issue-form">Issue ID ${icon('arrow')}</button></div><div id="issue-form"></div>${codexIds.length?`<div class="panel attendance-list">${codexIds.map(id=>`<div class="attendance-row"><div><strong>${escapeHtml(id.codex_id)}</strong><small>${escapeHtml(id.user?.full_name||'Unknown')} · ${fmtDate(id.issued_at)}</small></div><div class="codex-status ${id.status}">${escapeHtml(id.status)}</div><div class="action-row">${actionButton(id.status==='active'?'Suspend':id.status==='suspended'?'Activate':'View',id.status==='active'?'suspend-id':id.status==='suspended'?'activate-id':'view-id',id.id)}</div></div>`).join('')}</div>`:'<div class="empty-state"><h3>No Codex IDs issued</h3><p class="muted">Issue student IDs to enable attendance tracking.</p></div>'}`;
          bind();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='all-sessions') {
        target.innerHTML=loading('Loading all sessions...');
        try {
          const data=await api.get('/admin/attendance/sessions');
          const sessions=data.sessions||[];
          target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">ALL ATTENDANCE SESSIONS</div><h1>Event Sessions</h1><p class="muted">View and manage all attendance sessions across the academy.</p></div></div>${sessions.length?`<div class="panel attendance-list">${sessions.map(session=>`<div class="attendance-row"><div><strong>${escapeHtml(session.title)}</strong><small>${escapeHtml(session.session_type)} · ${escapeHtml(session.creator?.full_name||'Unknown')} · ${fmtDate(session.starts_at)} · ${session.records_count||0} records</small></div><div class="session-status ${session.status}">${escapeHtml(session.status)}</div><div class="action-row">${actionButton(session.status==='draft'?'Activate':session.status==='active'?'Close':'View',session.status==='draft'?'activate-session':session.status==='active'?'close-session':'view-session',session.id)}</div></div>`).join('')}</div>`:'<div class="empty-state"><h3>No sessions created</h3><p class="muted">Attendance sessions will appear here once created by instructors.</p></div>'}`;
          bind();
        } catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      } else if (route==='admin') {
        const target=document.querySelector('.app-content'); target.innerHTML=loading('Loading administration reports...');
        try { const [coursesData, apps, enrollments, payments, categories]=await Promise.all([api.get('/admin/courses/pending'),api.get('/admin/instructor-applications'),api.get('/admin/enrollments'),api.get('/admin/payments'),api.get('/categories')]); target.innerHTML=adminWorkspace({courses:coursesData,apps,enrollments,payments,categories}); bind(); }
        catch(error) { target.innerHTML=errorState(error.message,route); bind(); }
      }
    }
    function courseDetailLive(c, modules) { return `<main class="detail-page"><div class="shell"><a class="back-link" data-route="catalog">← Back to courses</a><div class="detail-grid"><div><div class="detail-video ${c.color}">${courseThumb(c)}<span>${c.icon}</span><small>Course preview</small></div><div class="detail-content"><div class="eyebrow green-text">${escapeHtml(c.category)} · ${escapeHtml(c.lang)}</div><h1>${escapeHtml(c.title)}</h1>${c.subtitle ? `<p class="detail-lead"><strong>${escapeHtml(c.subtitle)}</strong></p>` : ''}<p class="detail-lead">${escapeHtml(c.description || 'Build practical skills with a structured course from Codex Cybersquad Academy.')}</p><div class="detail-byline"><span>Created by <strong>${escapeHtml(c.instructor)}</strong></span><span>${escapeHtml(c.level)}</span><span>${escapeHtml(c.duration)}</span></div><h2>Course curriculum</h2><div class="curriculum">${modules || '<div class="empty-state">No lessons published yet.</div>'}</div></div></div><aside class="enroll-card"><div class="enroll-price">${fmt(c.price)}</div><p class="discount">${c.price?'Secure Paystack checkout':'Free course'}</p>${button(c.price?'Continue to payment':'Enroll for free',`checkout:${c.id}`,'btn btn-primary btn-wide')}<p class="secure">Payment verification is handled by the academy.</p></aside></div></div></main>`; }
    function checkoutLive(c) { return `<main class="checkout-page"><div class="shell checkout-layout"><div class="checkout-main"><a class="back-link" data-route="course:${encodeURIComponent(c.id)}">← Back to course</a><h1>Complete your enrollment</h1><p class="muted">The backend will calculate the final course price securely.</p></div><aside class="order-card"><div class="eyebrow green-text">Order summary</div><div class="order-course"><strong>${escapeHtml(c.title)}</strong></div><div class="summary-total"><span>Total</span><strong>${fmt(c.price)}</strong></div><button class="btn btn-primary btn-wide" data-action="pay">${c.price?'Continue with Paystack':'Enroll for free'} ${icon('arrow')}</button><p class="secure">Payment verification is handled by Codex Cybersquad Academy.</p></aside></div></main>`; }
    function learningLive(data) { const c=liveCourse(data.course||{}); const modules=data.modules||[]; const lessons=modules.flatMap(module=>module.lessons||[]); return `<div class="learn-layout"><aside class="learn-sidebar"><div class="learn-brand">${logo()}</div><a data-route="dashboard">← Back to dashboard</a><div class="learn-course-title"><div class="eyebrow">YOUR COURSE</div><h3>${escapeHtml(c.title)}</h3><div class="progress-line"><span style="width:${data.progress?.progress_percentage||0}%"></span></div><small>${data.progress?.progress_percentage||0}% complete</small></div><div class="lesson-list">${lessons.length?lessons.map((lesson,index)=>`<a data-action="lesson" data-lesson="${lesson.id}" class="${index===0?'current':''}"><span>${lesson.completed?'✓':index+1}</span>${escapeHtml(lesson.title)}<small>${lesson.completed?'Done':''}</small></a>`).join(''):'<div class="empty-state">No lessons available.</div>'}</div></aside><main class="learn-main"><div class="lesson-copy"><div class="eyebrow green-text">${modules.length} modules · ${lessons.length} lessons</div><h1>${escapeHtml(lessons[0]?.title||'Course learning')}</h1><p>${escapeHtml(lessons[0]?.description||'Select a lesson to begin learning.')}</p>${lessons[0]?resourcesBlock(lessons[0]):''}<div class="lesson-nav">${lessons[0]?`<button class="btn btn-primary" data-action="complete" data-lesson="${lessons[0].id}">Mark as complete ${icon('check')}</button>`:''}</div></div></main></div>`; }
    window.__hydratePage = hydratePage;
    state.courses = (data.courses || []).map(apiCourse);
    coursesStale = false;
    state.error = '';
  } catch (error) {
    state.error = error.message;
  }
}
async function loadCategories() { try { const data=await api.get('/categories'); state.categories=data.categories||[]; } catch(error) { state.error=state.error||error.message; } finally { categoriesLoaded = true; } }
async function applyCatalogFilters() {
  const filters = state.filters || { language: '', level: '', price: '' };
  const params = new URLSearchParams();
  if (filters.language) params.set('language', filters.language);
  if (filters.level) params.set('level', filters.level);
  if (filters.price === 'under') params.set('max_price', '10000');
  else if (filters.price === 'over') params.set('min_price', '10000');
  const query = params.toString();
  try { const data = await api.get(`/courses${query ? `?${query}` : ''}`); state.courses = (data.courses || []).map(apiCourse); state.error = ''; coursesStale = false; } catch (error) { state.error = error.message; }
  render();
}
async function applyCategory(categoryId) { state.categoryId=categoryId?Number(categoryId):null; state.category=state.categoryId?state.categories.find(item=>item.id===state.categoryId)?.name||'All':'All'; if(!state.categoryId) { await loadCourses(); render(); return; } try { const data=await api.get(`/categories/${state.categoryId}/courses`); state.courses=(data.courses||[]).map(apiCourse); state.error=''; render(); } catch(error) { state.error=error.message; render(); } }

function actionButton(label, action, id, cls = 'btn btn-small btn-outline') { return `<button class="${cls}" data-action="${action}" data-id="${id}">${label}</button>`; }
function instructorWorkspace(coursesData) {
  const items = coursesData.courses || [];
  return `<div class="page-intro"><div><div class="eyebrow green-text">INSTRUCTOR WORKSPACE</div><h1>Your courses</h1><p class="muted">Manage only courses owned by your authenticated account.</p></div><button class="btn btn-primary" data-action="show-course-form">Create course ${icon('arrow')}</button></div><div id="instructor-course-form"></div>${items.length ? `<div class="course-grid">${items.map(course => { const c=apiCourse(course); const modules=course.modules||[]; const lessons=modules.reduce((count,module)=>count+(module.lessons||[]).length,0); return `<article class="course-card"><div class="course-body"><div class="eyebrow">${escapeHtml(c.status)}</div><h3>${escapeHtml(c.title)}</h3><p class="muted">${escapeHtml(c.subtitle||c.description||'')}</p><div class="course-meta"><span>${fmt(c.price)}</span><span>${escapeHtml(c.language||c.lang)}</span><span>${modules.length} modules · ${lessons} lessons</span></div>${c.status==='rejected'&&course.admin_note?`<p class="admin-note-hint"><strong>Admin note:</strong> ${escapeHtml(course.admin_note)} — revise the course and submit it for review again.</p>`:''}<div class="action-row">${actionButton('Edit','edit-course',c.id)}${actionButton('Delete','delete-course',c.id)}${['draft','rejected'].includes(c.status)&&modules.length?actionButton('Submit','submit-course',c.id):''}</div></div></article>`}).join('')}</div>` : '<div class="empty-state"><h3>No courses yet.</h3><p class="muted">Create a course to begin teaching.</p></div>'}`;
}
function instructorApplication(application) {
  if (application) {
    return `<div class="page-intro"><div><div class="eyebrow green-text">INSTRUCTOR APPLICATION</div><h1>Application status</h1><p class="muted">Your application is currently <strong>${escapeHtml(application.status)}</strong>.</p></div></div><div class="panel application-status"><h2>${escapeHtml(application.expertise||'Instructor application')}</h2><p>${escapeHtml(application.bio||'')}</p><small>${escapeHtml(application.admin_note||'The academy will contact you with the next step.')}</small></div>`;
  }
  return `<div class="page-intro"><div><div class="eyebrow green-text">BECOME AN INSTRUCTOR</div><h1>Share your knowledge. Impact lives.</h1><p class="muted">Apply to teach practical skills to ambitious learners across Northern Nigeria.</p></div></div><div class="instructor-form-layout"><div class="form-panel"><h2>Tell us about yourself</h2><div class="form-grid"><label>Phone number<input data-field="phone" placeholder="0800 000 0000"></label><label>Area of expertise<input data-field="expertise" placeholder="e.g. Web development"></label></div><label>Experience<textarea data-field="experience" placeholder="Describe your teaching or professional experience"></textarea></label><label>Short bio<textarea data-field="bio" placeholder="Tell us about your experience..."></textarea></label><button class="btn btn-primary" data-action="apply">Submit application ${icon('arrow')}</button></div></div>`;
}
function courseForm(course = {}, categories = []) {
  const publishedNote = ['published', 'approved'].includes(course.status)
    ? `<p class="form-help">This course is live. Saving changes will move it to <strong>pending</strong> for admin re-review before it returns to the catalog.</p>`
    : course.status === 'pending'
      ? `<p class="form-help">This course is awaiting admin review. You can keep editing while it is pending.</p>`
      : course.status === 'rejected'
        ? `<p class="form-help admin-note-hint">This course was <strong>rejected</strong>${course.admin_note ? ` — <strong>Admin note:</strong> ${escapeHtml(course.admin_note)}` : ''}. Please revise the course and submit it for review again.</p>`
        : '';
  return `<div class="form-panel" data-course-form="${course.id||''}"><h2>${course.id?'Edit course':'Create a course'}</h2>${publishedNote}<div class="form-grid"><label>Title<input data-field="title" value="${escapeHtml(course.title)}"></label><label>Category<select data-field="category_id">${categories.map(category=>`<option value="${category.id}" ${category.id===course.category?.id||category.id===course.category_id?'selected':''}>${escapeHtml(category.name)}</option>`).join('')}</select></label><label>Language<select data-field="language"><option value="english" ${course.language==='english'?'selected':''}>English</option><option value="hausa" ${course.language==='hausa'?'selected':''}>Hausa</option></select></label><label>Level<select data-field="level"><option value="beginner" ${course.level==='beginner'?'selected':''}>Beginner</option><option value="intermediate" ${course.level==='intermediate'?'selected':''}>Intermediate</option><option value="advanced" ${course.level==='advanced'?'selected':''}>Advanced</option></select></label><label>Price<input data-field="price" type="number" min="0" step="0.01" value="${escapeHtml(course.price??0)}"></label><label>Duration (minutes)<input data-field="duration" type="number" min="0" value="${escapeHtml(course.duration??0)}"></label></div><label>Subtitle<input data-field="subtitle" value="${escapeHtml(course.subtitle)}"></label><label>Description<textarea data-field="description">${escapeHtml(course.description)}</textarea></label><label>Thumbnail image URL<input data-field="thumbnail" maxlength="${THUMBNAIL_MAX_LENGTH}" value="${escapeHtml(course.thumbnail)}" placeholder="https://example.com/course-thumbnail.jpg"></label><p class="form-help">Use a direct image URL for the course card (for example <code>https://example.com/course-thumbnail.jpg</code> or <code>https://img.youtube.com/vi/VIDEO_ID/hqdefault.jpg</code>) rather than a Bing/Google Images search or detail page link. Do not paste a YouTube watch link here — lesson videos use the lesson Video URL field. Maximum ${THUMBNAIL_MAX_LENGTH} characters.</p><div class="action-row"><button class="btn btn-primary" data-action="save-course" data-id="${course.id||''}">${course.id?'Save changes':'Create course'}</button>${course.id?actionButton('Load curriculum','load-editor',course.id):''}</div></div>`;
}
function moduleEditor(course) {
  const modules=course.modules||[];
  const nextModuleOrder = modules.reduce((max, module) => Math.max(max, Number(module.order)||0), 0) + 1;
  return `<div class="panel editor-panel" data-next-module-order="${nextModuleOrder}"><div class="section-heading compact-heading"><h2>Curriculum</h2>${actionButton('Add module','show-module-form',course.id,'btn btn-small btn-primary')}</div><div id="module-form"></div>${modules.length?modules.map(module=>{ const nextLessonOrder=(module.lessons||[]).reduce((max, lesson)=>Math.max(max, Number(lesson.order)||0),0)+1; return `<div class="editor-item" data-module-id="${module.id}" data-next-lesson-order="${nextLessonOrder}"><div><strong>${escapeHtml(module.title)}</strong><small>${(module.lessons||[]).length} lessons · order ${module.order}${module.description?` · ${escapeHtml(module.description)}`:''}</small></div><div class="action-row">${actionButton('Edit','edit-module',module.id)}${actionButton('Delete','delete-module',module.id)}</div><div class="lesson-items">${(module.lessons||[]).map(lesson=>`<div class="editor-subitem"><span>${escapeHtml(lesson.title)} · ${lesson.duration||0} min</span><div class="action-row">${actionButton('Edit','edit-lesson',lesson.id)}${actionButton('Delete','delete-lesson',lesson.id)}${actionButton('Resource','show-resource-form',lesson.id)}</div></div>`).join('')}<div id="lesson-form-${module.id}"></div>${actionButton('Add lesson','show-lesson-form',module.id,'btn btn-small btn-outline')}</div></div>`;}).join(''):'<div class="empty-state">No modules yet.</div>'}</div>`;
}
function adminWorkspace(data) { const pending=data.courses?.courses||[]; const applications=data.apps?.applications||[]; const enrollments=data.enrollments?.enrollments||[]; const payments=data.payments?.payments||[]; const totals=data.payments?.aggregates||{}; const categories=data.categories?.categories||[]; return `<div class="page-intro"><div><div class="eyebrow green-text">ADMIN CONSOLE</div><h1>Administration</h1><p class="muted">Live platform operations and reports.</p></div></div><div class="metric-grid admin-metrics"><div class="metric-card"><strong>${pending.length}</strong><small>Pending courses</small></div><div class="metric-card"><strong>${applications.length}</strong><small>Applications</small></div><div class="metric-card"><strong>${enrollments.length}</strong><small>Enrollments</small></div><div class="metric-card"><strong>${fmt(totals.total_successful_revenue||0)}</strong><small>Successful revenue</small></div></div><div class="admin-grid"><div class="panel table-panel"><div class="section-heading compact-heading"><h3>Pending courses</h3></div>${pending.length?pending.map(course=>`<div class="pending-row"><div><strong>${escapeHtml(course.title)}</strong><small>${escapeHtml(course.status)} · ${escapeHtml(course.instructor?.full_name||'')}</small></div><div class="action-row">${actionButton('Approve','approve-course',course.id)}${actionButton('Reject','reject-course',course.id)}</div></div>`).join(''):'<div class="empty-state">No pending courses.</div>'}</div><div class="panel table-panel"><div class="section-heading compact-heading"><h3>Instructor applications</h3></div>${applications.length?applications.map(application=>`<div class="pending-row"><div><strong>${escapeHtml(application.user?.full_name||`Application ${application.id}`)}</strong><small>${escapeHtml(application.status)} · ${escapeHtml(application.expertise||'')}</small></div><div class="action-row">${application.status==='pending'?`${actionButton('Approve','approve-application',application.id)}${actionButton('Reject','reject-application',application.id)}`:''}</div></div>`).join(''):'<div class="empty-state">No applications.</div>'}</div><div class="panel table-panel"><div class="section-heading compact-heading"><h3>Enrollments</h3></div>${enrollments.length?enrollments.slice(0,10).map(item=>`<div class="pending-row"><div><strong>${escapeHtml(item.course?.title||`Course ${item.course_id}`)}</strong><small>${escapeHtml(item.student?.full_name||`Student ${item.student_id}`)} · ${escapeHtml(item.status)}</small></div></div>`).join(''):'<div class="empty-state">No enrollments.</div>'}</div><div class="panel table-panel"><div class="section-heading compact-heading"><h3>Payments</h3></div>${payments.length?payments.slice(0,10).map(payment=>`<div class="pending-row"><div><strong>${escapeHtml(payment.course?.title||payment.reference)}</strong><small>${escapeHtml(payment.status)} · ${fmt(payment.amount)}</small></div></div>`).join(''):'<div class="empty-state">No payments.</div>'}</div><div class="panel table-panel"><div class="section-heading compact-heading"><h3>Categories</h3><button class="btn btn-small btn-primary" data-action="show-category-form">Add category</button></div><div id="category-form"></div><p class="muted">${categories.length?categories.map(category=>escapeHtml(category.name)).join(' · '):'No categories.'}</p></div></div>`; }
async function refreshInstructor() {
  const target=document.querySelector('.app-content');
  if(!target) return;
  if (currentRole() !== 'instructor') {
    window.__hydratePage?.();
    return;
  }
  target.innerHTML=loading('Loading instructor courses...');
  try {
    const data=await api.get('/instructor/courses');
    const application=await api.get('/instructor/application').catch(()=>({application:null}));
    target.innerHTML=`${instructorWorkspace(data)}<div class="panel application-status"><h3>Application status</h3><p class="muted">${escapeHtml(application.application?.status||'Approved instructor')}</p></div>`;
    bind();
  } catch(error) {
    target.innerHTML=errorState(error.message,'instructor');
    bind();
  }
}
async function refreshAdmin() { const target=document.querySelector('.app-content'); if(!target)return; target.innerHTML=loading('Loading administration reports...'); try { const [coursesData,apps,enrollments,payments,categories]=await Promise.all([api.get('/admin/courses/pending'),api.get('/admin/instructor-applications'),api.get('/admin/enrollments'),api.get('/admin/payments'),api.get('/categories')]); target.innerHTML=adminWorkspace({courses:coursesData,apps,enrollments,payments,categories}); bind(); } catch(error) { target.innerHTML=errorState(error.message,'admin'); bind(); } }
async function refreshCourseEditor(courseId) { const target=document.querySelector('.app-content'); if(!target)return; target.innerHTML=loading('Loading course editor...'); try { const data=await api.get(`/instructor/courses/${Number(courseId)}`); const course=data.course; target.innerHTML=`<div class="page-intro"><div><div class="eyebrow green-text">COURSE EDITOR</div><h1>${escapeHtml(course.title)}</h1><p class="muted">${escapeHtml(course.status)}</p></div>${actionButton('Back to courses','back-instructor','x','btn btn-small btn-outline')}</div>${courseForm(course,state.categories)}${moduleEditor(course)}`; bind(); } catch(error) { target.innerHTML=errorState(error.message,`edit-course:${courseId}`); bind(); } }
function showModal(title, message, action, id) { const existing=document.querySelector('.confirmation-modal'); existing?.remove(); document.body.insertAdjacentHTML('beforeend',`<div class="confirmation-modal" role="dialog" aria-modal="true"><div class="modal-card"><h2>${escapeHtml(title)}</h2><p>${escapeHtml(message)}</p><div class="action-row"><button class="btn btn-outline" data-action="close-modal">Cancel</button><button class="btn btn-primary" data-action="confirm-action" data-action-type="${action}" data-id="${id}">Confirm</button></div></div></div>`); bind(); }
async function crudAction(action,id) { try { if(action==='delete-course') await api.delete(`/instructor/courses/${Number(id)}`); if(action==='submit-course') await api.post(`/instructor/courses/${Number(id)}/submit`,{}); if(action==='approve-course') await api.patch(`/admin/courses/${Number(id)}/approve`,{}); if(action==='reject-course') await api.patch(`/admin/courses/${Number(id)}/reject`,{}); if(action==='approve-application') await api.patch(`/admin/instructor-applications/${Number(id)}/approve`,{}); if(action==='reject-application') await api.patch(`/admin/instructor-applications/${Number(id)}/reject`,{}); if(action==='application-decision') await api.patch(`/admin/instructor-applications/${Number(id)}/${document.querySelector('.confirmation-modal')?.dataset.decision||'approve'}`,{}); if(action==='delete-module') await api.delete(`/instructor/modules/${Number(id)}`); if(action==='delete-lesson') await api.delete(`/instructor/lessons/${Number(id)}`); if(['submit-course','approve-course','reject-course','delete-module','delete-lesson'].includes(action)) coursesStale = true; toast('Action completed successfully.'); if(['delete-module','delete-lesson'].includes(action)){ refreshCourseEditor(state.page.split(':')[1]); return; } state.page=action.includes('course')&&action!=='approve-course'&&action!=='reject-course'?'instructor':'admin'; render(); action.includes('course')&&action!=='approve-course'&&action!=='reject-course'?refreshInstructor():refreshAdmin(); } catch(error) { toast(error.message); } }
async function saveCourse(event) { event.preventDefault(); const form=document.querySelector('[data-course-form]'); const value=field=>form.querySelector(`[data-field="${field}"]`)?.value; const body={title:value('title'),category_id:Number(value('category_id')),language:value('language'),level:value('level'),price:Number(value('price')||0),duration:Number(value('duration')||0),subtitle:value('subtitle'),description:value('description'),thumbnail:value('thumbnail')}; if(body.thumbnail && body.thumbnail.length > THUMBNAIL_MAX_LENGTH) { toast(`Thumbnail URL must be ${THUMBNAIL_MAX_LENGTH} characters or less.`); return; } try { if(form.dataset.courseForm) { const data=await api.put(`/instructor/courses/${Number(form.dataset.courseForm)}`,body); coursesStale = true; toast(data.course?.status==='pending'?'Course updated and submitted for admin re-review.':'Course saved successfully.'); refreshCourseEditor(form.dataset.courseForm); } else { await api.post('/instructor/courses',body); coursesStale = true; toast('Course saved successfully.'); refreshInstructor(); } } catch(error) { toast(error.message); } }
async function saveModule(event) { event.preventDefault(); const form=document.querySelector('#module-form form'); const id=form.dataset.id; const body={title:form.querySelector('[name=title]').value,description:form.querySelector('[name=description]').value,order:Number(form.querySelector('[name=order]').value)}; try { if(id) await api.put(`/instructor/modules/${Number(id)}`,body); else await api.post(`/instructor/courses/${Number(form.dataset.course)}/modules`,body); coursesStale = true; toast('Module saved.'); refreshCourseEditor(state.page.split(':')[1]); } catch(error) { toast(error.message); } }
async function saveLesson(event) { event.preventDefault(); const form=event.currentTarget; const body={title:form.querySelector('[name=title]').value,description:form.querySelector('[name=description]').value,video_url:form.querySelector('[name=video_url]').value,duration:Number(form.querySelector('[name=duration]').value),order:Number(form.querySelector('[name=order]').value),is_preview:form.querySelector('[name=is_preview]').checked}; try { if(form.dataset.id) await api.put(`/instructor/lessons/${Number(form.dataset.id)}`,body); else await api.post(`/instructor/modules/${Number(form.dataset.module)}/lessons`,body); coursesStale = true; toast('Lesson saved.'); refreshCourseEditor(state.page.split(':')[1]); } catch(error) { toast(error.message); } }
async function saveResource(event) { event.preventDefault(); const form=event.currentTarget; try { await api.post(`/instructor/lessons/${Number(form.dataset.lesson)}/resources`,{name:form.querySelector('[name=name]').value,file_url:form.querySelector('[name=file_url]').value,file_type:form.querySelector('[name=file_type]').value}); coursesStale = true; toast('Resource added.'); refreshCourseEditor(state.page.split(':')[1]); } catch(error) { toast(error.message); } }
async function saveCategory(event) { event.preventDefault(); const name=document.querySelector('#category-form [name=name]').value; try { await api.post('/admin/categories',{name}); toast('Category created.'); refreshAdmin(); } catch(error) { toast(error.message); } }
async function editCurriculumItem(type,id) { try { const data=await api.get(`/instructor/courses/${Number(state.page.split(':')[1])}`); const modules=data.course?.modules||[]; const item=type==='module'?modules.find(module=>module.id===Number(id)):modules.flatMap(module=>module.lessons||[]).find(lesson=>lesson.id===Number(id)); if(!item) return toast('Curriculum item was not found.'); if(type==='module') { const host=document.querySelector('#module-form'); host.innerHTML=`<form data-id="${item.id}"><input name="title" value="${escapeHtml(item.title)}" required><input name="description" value="${escapeHtml(item.description)}"><label>Order<input name="order" type="number" min="0" value="${item.order}"></label><button class="btn btn-small btn-primary">Save module</button></form>`; host.querySelector('form').addEventListener('submit',saveModule); } else { const host=document.querySelector(`#lesson-form-${item.module_id}`); host.innerHTML=`<form data-id="${item.id}" data-module="${item.module_id}"><input name="title" value="${escapeHtml(item.title)}" required><input name="description" value="${escapeHtml(item.description)}"><label>Lesson video URL<input name="video_url" value="${escapeHtml(item.video_url)}" placeholder="https://www.youtube.com/watch?v=VIDEO_ID"></label><p class="form-help">Paste a YouTube watch, youtu.be, or embed URL. This is separate from the course thumbnail image.</p><input name="duration" type="number" min="0" value="${item.duration}"><input name="order" type="number" min="0" value="${item.order}"><label><input name="is_preview" type="checkbox" ${item.is_preview?'checked':''}> Preview</label><button class="btn btn-small btn-primary">Save lesson</button></form>`; host.querySelector('form').addEventListener('submit',saveLesson); } } catch(error) { toast(error.message); } }
function showModuleForm(event) { const host=document.querySelector('#module-form'); const course=event.currentTarget.dataset.id; const nextOrder=Number(document.querySelector('.editor-panel')?.dataset.nextModuleOrder||1); host.innerHTML=`<form data-course="${course}"><input name="title" placeholder="Module title" required><input name="description" placeholder="Description"><label>Order<input name="order" type="number" min="0" value="${nextOrder}" required></label><p class="form-help">Order must be unique within this course. Suggested next order: ${nextOrder}.</p><button class="btn btn-small btn-primary">Save module</button></form>`; host.querySelector('form').addEventListener('submit',saveModule); }
function showLessonForm(event) { const moduleId=event.currentTarget.dataset.id; const host=document.querySelector(`#lesson-form-${moduleId}`); const nextOrder=Number(event.currentTarget.closest('.editor-item')?.dataset.nextLessonOrder||1); host.innerHTML=`<form data-module="${moduleId}"><input name="title" placeholder="Lesson title" required><input name="description" placeholder="Description"><label>Lesson video URL<input name="video_url" placeholder="https://www.youtube.com/watch?v=VIDEO_ID"></label><p class="form-help">Use a YouTube URL here. Course thumbnail images belong in the Thumbnail image URL field above.</p><input name="duration" type="number" min="0" value="0"><label>Order<input name="order" type="number" min="0" value="${nextOrder}"></label><p class="form-help">Order must be unique within this module. Suggested next order: ${nextOrder}.</p><label><input name="is_preview" type="checkbox"> Preview lesson</label><button class="btn btn-small btn-primary">Save lesson</button></form>`; host.querySelector('form').addEventListener('submit',saveLesson); }
function showResourceForm(event) { const host=event.currentTarget.closest('.editor-subitem'); host.insertAdjacentHTML('beforeend',`<form class="resource-form" data-lesson="${event.currentTarget.dataset.id}"><input name="name" placeholder="Resource name" required><input name="file_url" placeholder="File URL" required><input name="file_type" placeholder="pdf" required><button class="btn btn-small btn-primary">Add resource</button></form>`); host.querySelector('form').addEventListener('submit',saveResource); }
function showCategoryForm() { const host=document.querySelector('#category-form'); host.innerHTML='<form><input name="name" placeholder="Category name" required><button class="btn btn-small btn-primary">Create category</button></form>'; host.querySelector('form').addEventListener('submit',saveCategory); }

// QR Scanner
let html5QrCode = null;
let isScanning = false;
let lastScannedToken = null;
let scanCooldown = false;

function initQrScanner() {
  const startBtn = document.getElementById('start-scanner');
  const stopBtn = document.getElementById('stop-scanner');
  if (!startBtn || !stopBtn) return;
  
  startBtn.addEventListener('click', startCamera);
  stopBtn.addEventListener('click', stopCamera);
}

async function startCamera() {
  if (isScanning || scanCooldown) return;
  
  const qrReader = document.getElementById('qr-reader');
  if (!qrReader) return;
  
  try {
    html5QrCode = new Html5Qrcode('qr-reader');
    const config = { fps: 10, qrbox: { width: 250, height: 250 } };
    
    await html5QrCode.start({ facingMode: 'environment' }, config, onScanSuccess, onScanFailure);
    
    isScanning = true;
    document.getElementById('start-scanner').style.display = 'none';
    document.getElementById('stop-scanner').style.display = 'inline-block';
    document.getElementById('scan-results').innerHTML = '<p class="muted">Camera active. Point at a student QR code.</p>';
  } catch (error) {
    toast('Unable to start camera. Please ensure camera permission is granted.');
    console.error('Camera start error:', error);
  }
}

async function stopCamera() {
  if (!isScanning || !html5QrCode) return;
  
  try {
    await html5QrCode.stop();
    isScanning = false;
    document.getElementById('start-scanner').style.display = 'inline-block';
    document.getElementById('stop-scanner').style.display = 'none';
    document.getElementById('scan-results').innerHTML = '<p class="muted">Camera stopped. Click "Start Camera" to scan again.</p>';
  } catch (error) {
    console.error('Camera stop error:', error);
  }
}

async function onScanSuccess(decodedText, decodedResult) {
  if (scanCooldown || lastScannedToken === decodedText) return;
  
  scanCooldown = true;
  lastScannedToken = decodedText;
  
  // Pause scanning temporarily
  if (html5QrCode && isScanning) {
    try {
      await html5QrCode.pause();
    } catch (e) {
      console.error('Pause error:', e);
    }
  }
  
  const resultsDiv = document.getElementById('scan-results');
  resultsDiv.innerHTML = loading('Processing QR code...');
  
  try {
    const mode = document.querySelector('input[name="scan-mode"]:checked')?.value || 'verify';
    const sessionId = document.getElementById('session-select')?.value;
    
    if (mode === 'verify' || !sessionId) {
      // Verification mode
      const role = currentRole();
      const verifyEndpoint = role === 'admin' ? `/admin/codex-id/verify/${decodedText}` : `/instructor/codex-id/verify/${decodedText}`;
      const data = await api.get(verifyEndpoint);
      
      const status = data.codex_id?.status || 'unknown';
      const statusClass = status === 'active' ? 'active' : status === 'suspended' ? 'suspended' : 'revoked';
      
      resultsDiv.innerHTML = `
        <div class="scan-result-card">
          <h3>Student Verified</h3>
          <div class="scan-result-field"><strong>Codex ID:</strong> ${escapeHtml(data.codex_id?.codex_id || 'Unknown')}</div>
          <div class="scan-result-field"><strong>Status:</strong> <span class="codex-status ${statusClass}">${escapeHtml(status.toUpperCase())}</span></div>
          <div class="scan-result-field"><strong>Issued:</strong> ${fmtDate(data.codex_id?.issued_at)}</div>
          <button class="btn btn-small btn-outline" id="scan-again">Scan Again</button>
        </div>
      `;
    } else {
      // Attendance recording mode
      const role = currentRole();
      const scanEndpoint = role === 'admin' ? `/admin/attendance/sessions/${sessionId}/scan` : `/instructor/attendance/sessions/${sessionId}/scan`;
      const data = await api.post(scanEndpoint, { qr_token: decodedText });
      
      resultsDiv.innerHTML = `
        <div class="scan-result-card">
          <h3>Attendance Recorded</h3>
          <div class="scan-result-field"><strong>Student:</strong> ${escapeHtml(data.record?.student?.codex_id || 'Unknown')}</div>
          <div class="scan-result-field"><strong>Status:</strong> <span class="attendance-status present">PRESENT</span></div>
          <div class="scan-result-field"><strong>Scanned at:</strong> ${fmtDate(data.record?.scanned_at)}</div>
          <button class="btn btn-small btn-outline" id="scan-again">Scan Again</button>
        </div>
      `;
    }
    
    bind();
  } catch (error) {
    let message = error.message;
    if (error.status === 409) {
      message = 'Already recorded for this session';
    } else if (error.status === 404) {
      message = 'Invalid QR code - student not found';
    } else if (error.code === 'ID_SUSPENDED') {
      message = 'Student ID is suspended - attendance not recorded';
    } else if (error.code === 'ID_REVOKED') {
      message = 'Student ID is revoked - attendance not recorded';
    } else if (error.code === 'ACCOUNT_INACTIVE') {
      message = 'Student account is inactive - attendance not recorded';
    }
    
    resultsDiv.innerHTML = `
      <div class="scan-result-card error">
        <h3>Scan Failed</h3>
        <p class="error-text">${escapeHtml(message)}</p>
        <button class="btn btn-small btn-outline" id="scan-again">Scan Again</button>
      </div>
    `;
    bind();
  }
}

function onScanFailure(error) {
  // Ignore scan failures (no QR in view)
}

function icon(name) { return ({search:'⌕', bell:'♧', menu:'☰', arrow:'→', check:'✓', clock:'◷', play:'▶', star:'★', heart:'♡', lock:'⌑', users:'♧', certificate:'▱'}[name] || name); }
function logo() { return `<a class="logo" data-route="home"><img class="logo-img" src="/branding/codex-cybersquad-logo.png" alt="Codex Cybersquad Technologies Ltd Logo - Innovate. Secure. Empower." width="160" height="160" /><span>Codex Cybersquad Academy</span></a>`; }
function button(label, route, cls='btn btn-primary') { return `<button class="${cls}" ${route ? `data-route="${route}"` : ''}>${label}</button>`; }
function courseThumb(c, cls = 'course-thumb') {
  const url = String(c.thumbnail || '').trim();
  if (!/^https?:\/\//i.test(url)) return '';
  return `<img class="${cls}" src="${escapeHtml(url)}" alt="${escapeHtml(c.title || 'Course')} preview" loading="lazy" onerror="this.remove()">`;
}
function courseCard(c, compact=false) { const count = Number(c.students); const studentsLabel = c.students === '' || c.students == null || Number.isNaN(count) ? '' : `<span>${icon('users')} ${count} ${count === 1 ? 'student' : 'students'}</span>`; return `<article class="course-card ${compact?'compact':''}">
  <div class="course-art ${escapeHtml(c.color)}">${courseThumb(c)}<span class="art-icon">${escapeHtml(c.icon)}</span><span class="art-label">${escapeHtml(c.category)}</span><button class="wish">${icon('heart')}</button></div>
  <div class="course-body"><div class="eyebrow">${escapeHtml(c.lang)} · ${escapeHtml(c.level)}</div><h3>${escapeHtml(c.title)}</h3><p class="muted">${escapeHtml(c.instructor)}</p><div class="course-meta">${studentsLabel}<span>${icon('clock')} ${escapeHtml(c.duration)}</span></div><div class="course-price"><strong>${fmt(c.price)}</strong>${button('View course', `course:${encodeURIComponent(c.id)}`, 'btn btn-small btn-outline')}</div></div></article>`; }
function header() {
  const role = currentRole();
  const publicLinks = [['catalog', 'Explore Courses']];
  if (role === 'student') publicLinks.push(['dashboard', 'My Learning']);
  else if (role === 'instructor') publicLinks.push(['instructor', 'Instructor Workspace']);
  else if (role === 'admin') publicLinks.push(['admin', 'Admin Console']);
  else publicLinks.push(['instructor', 'Become an Instructor']);
  const actions = authState
    ? `<a data-route="${homeRouteForRole()}" class="login-link">${escapeHtml(authState.user?.full_name || 'Account')}</a>${button('Open workspace', homeRouteForRole(), 'btn btn-small')}`
    : `<a data-route="login" class="login-link">Log in</a>${button('Get started','register','btn btn-small')}`;
  return `<header class="topbar"><div class="shell nav-wrap">${logo()}<nav class="desktop-nav">${publicLinks.map(([r,l])=>`<a data-route="${r}">${l}</a>`).join('')}</nav><div class="nav-actions"><button class="icon-btn mobile-menu">${icon('menu')}</button><button class="icon-btn">${icon('search')}</button>${actions}</div></div></header>`;
}
function footer() {
  const instructorLink = currentRole() === 'instructor'
    ? `<a data-route="instructor">Instructor Workspace</a>`
    : currentRole() === 'admin'
      ? `<a data-route="admin">Admin Console</a>`
      : `<a data-route="instructor">Become an Instructor</a>`;
  return `<footer><div class="shell footer-grid"><div>${logo()}<p class="muted">Practical skills for a brighter future in Northern Nigeria.</p><div class="socials"><span>f</span><span>in</span><span>◎</span></div></div><div><h4>Explore</h4><a data-route="catalog">All Courses</a><a data-route="catalog">Categories</a>${instructorLink}</div><div><h4>Company</h4><a>About Codex Cybersquad Academy</a><a>Contact us</a><a>Privacy policy</a></div><div><h4>Stay in the loop</h4><p class="muted">Get new courses and learning tips in your inbox.</p><div class="subscribe"><input placeholder="Your email address"><button>→</button></div></div></div><div class="shell footer-bottom"><span>© 2026 Codex Cybersquad Academy</span><span>Built for learners in Nigeria</span></div></footer>`;
}

function homeCategories() {
  if (!categoriesLoaded && !state.categories.length) return '<div class="live-state" style="grid-column:1/-1"><span class="loader"></span><p>Loading categories...</p></div>';
  if (!state.categories.length) return '<div class="empty-state" style="grid-column:1/-1"><h3>No categories yet.</h3><p class="muted">Course categories will appear here once the academy publishes them.</p></div>';
  const iconFor = name => { const n = String(name).toLowerCase(); if (n.includes('web')) return '⌘'; if (n.includes('program') || n.includes('code')) return '</>'; if (n.includes('cyber') || n.includes('security')) return '◈'; if (n.includes('data') || n.includes('ai') || n.includes('science')) return '✣'; if (n.includes('design') || n.includes('graphic')) return '✦'; if (n.includes('market')) return '◒'; return '✦'; };
  return state.categories.map((category, index) => `<button class="category-card cat-${index % 6}" data-route="catalog"><span>${iconFor(category.name)}</span><strong>${escapeHtml(category.name)}</strong><small>Explore courses ${icon('arrow')}</small></button>`).join('');
}
function homeFeatured() {
  const items = catalogCourses().slice(0, 3);
  if (items.length) return items.map(courseCard).join('');
  return `<div class="empty-state" style="grid-column:1/-1"><h3>No courses available yet.</h3><p class="muted">${coursesStale ? 'Loading the latest courses...' : 'Fresh courses will appear here once published.'}</p></div>`;
}
function home() { return `${header()}<main><section class="hero"><div class="shell hero-grid"><div class="hero-copy"><div class="pill"><span class="pulse"></span> Northern Nigeria's learning community</div><h1>Learn skills.<br><em>Build your future.</em></h1><p class="hero-lead">Practical technology and digital skills, taught in Hausa and English — for the next generation of builders.</p><div class="hero-actions">${button('Explore courses '+icon('arrow'),'catalog')}${button('How it works',null,'btn btn-ghost')}</div><div class="trust-row"><div class="avatar-stack"><span>AM</span><span>MB</span><span>FS</span><span>ZI</span></div><div><strong>10,000+ learners</strong><small>already building their future</small></div></div></div><div class="hero-visual"><div class="hero-glow"></div><div class="hero-photo"><div class="photo-placeholder"><span>👩🏾‍💻</span><small>Learn. Practice. Grow.</small></div></div><div class="floating-card progress-float"><span class="float-icon green">✓</span><div><small>Course progress</small><strong>72% complete</strong></div><div class="mini-ring">72</div></div><div class="floating-card language-float"><span class="float-icon yellow">文</span><div><small>Learn your way</small><strong>Hausa + English</strong></div></div></div></div></section>
<section class="stats"><div class="shell stat-grid"><div><strong>Learn</strong><small>Practical skills</small></div><div><strong>Build</strong><small>Real projects</small></div><div><strong>Grow</strong><small>Career confidence</small></div><div><strong>Earn</strong><small>New opportunities</small></div></div></section>
<section class="section shell"><div class="section-heading"><div><div class="eyebrow green-text">Start learning today</div><h2>Skills that open doors.</h2></div><a data-route="catalog" class="text-link">Explore all courses ${icon('arrow')}</a></div><div class="category-grid">${homeCategories()}</div></section>
<section class="section section-soft"><div class="shell"><div class="section-heading"><div><div class="eyebrow green-text">Learner favourites</div><h2>Popular courses</h2></div></div><div class="course-grid">${homeFeatured()}</div></div></section>
<section class="section shell split-section"><div class="how-art"><div class="how-card"><span class="big-number">01</span><strong>Create your account</strong><p>Join a community of ambitious learners.</p></div><div class="how-card shifted"><span class="big-number">02</span><strong>Choose your path</strong><p>Learn from courses made for you.</p></div></div><div class="section-copy"><div class="eyebrow green-text">Learning made practical</div><h2>Go from curious to confident.</h2><p>Whether you're starting from zero or levelling up, CODEx gives you the skills, support and community to move forward.</p><ul class="check-list"><li><b>✓</b> Learn from anywhere, in Hausa or English</li><li><b>✓</b> Practice with real-world projects</li><li><b>✓</b> Earn a certificate you can be proud of</li></ul>${button('See how it works '+icon('arrow'),'catalog','btn btn-outline')}</div></section>
<section class="instructor-banner"><div class="shell instructor-inner"><div><div class="eyebrow">For the experts</div><h2>Share what you know.<br><em>Impact a life.</em></h2><p>Teach practical skills to ambitious learners across Nigeria — and earn while you do it.</p>${button('Become an instructor '+icon('arrow'),'instructor','btn btn-light')}</div><div class="instructor-art"><span>🎓</span><small>Teach · Inspire · Grow</small></div></div></section>
<section class="section shell testimonial"><div class="quote-mark">“</div><blockquote>Build practical skills at your own pace with courses designed for learners across Northern Nigeria.</blockquote><div class="quote-author"><span class="person-avatar">C</span><div><strong>Codex Cybersquad Academy</strong><small>Practical learning for your next step</small></div></div></section>
<section class="cta"><div class="shell"><h2>Your future is waiting.</h2><p>Start learning a skill that can change your tomorrow.</p>${button('Create your free account '+icon('arrow'),'register','btn btn-light')}</div></section></main>${footer()}`; }

function auth(type) { const register=type==='register'; return `<div class="auth-page"><div class="auth-brand">${logo()}</div><div class="auth-layout"><div class="auth-aside"><div class="eyebrow">CODEx Academy</div><h1>${register?'Start your learning journey.':'Welcome back, learner.'}</h1><p>${register?'Build practical skills, in your language, at your pace.':'Pick up where you left off and keep building your future.'}</p><div class="auth-quote">“I never thought tech was for me until CODEx made it feel possible.”<small>— Maryam, Kano</small></div></div><div class="auth-card"><a class="back-link" data-route="home">← Back to home</a><h2>${register?'Create your account':'Welcome back'}</h2><p class="muted">${register?'Create an account and start learning at your own pace.':'Log in to continue learning.'}</p>${register?'<label>Full name<input placeholder="e.g. Ibrahim Yusuf"></label>':''}<label>Email address<input type="email" placeholder="you@example.com"></label>${register?'<label>Phone number<input placeholder="0800 000 0000"></label>':''}<label>Password<input type="password" placeholder="At least 8 characters"></label>${register?'<label class="check-row"><input type="checkbox"> <span>I agree to the Terms & Conditions</span></label>':'<div class="form-row"><label class="check-row"><input type="checkbox"> <span>Remember me</span></label><a data-action="forgot-password">Forgot password?</a></div>'}<button class="btn btn-primary btn-wide" data-action="auth-submit">${register?'Create account':'Log in'}</button><div class="or"><span>or continue with</span></div>${button('G  Continue with Google',null,'btn btn-google btn-wide')}<p class="auth-switch">${register?'Already have an account?':'Don’t have an account?'} <a data-route="${register?'login':'register'}">${register?'Log in':'Create one'}</a></p></div></div></div>`; }

function appShell(active, content) {
  const items = navItemsForRole(currentRole());
  const activeKey = active.includes(':') ? active.split(':')[0] : active;
  return `<div class="app-layout"><aside class="sidebar">${logo()}<div class="side-label">MENU</div>${items.map(([r,ic,l])=>`<a data-route="${r}" class="${activeKey===r||active===r?'active':''}"><span>${ic}</span>${l}</a>`).join('')}<div class="side-label">ACCOUNT</div><a data-route="${homeRouteForRole()}"><span>⚙</span>Profile</a><div class="sidebar-bottom"><div class="mini-profile"><span>${(authState?.user?.full_name||'CS').slice(0,2).toUpperCase()}</span><div><strong>${escapeHtml(authState?.user?.full_name||'Learner')}</strong><small>${escapeHtml(authState?.user?.role||'Guest')} account</small></div></div><a data-action="logout"><span>↪</span>Log out</a></div></aside><main class="app-main"><div class="mobile-appbar">${logo()}<button class="icon-btn">☰</button></div><div class="shell app-content">${content}</div></main></div>`;
}
function catalog() { const available=catalogCourses(); const list=available.filter(c=>(state.category==='All'||c.category===state.category)&&c.title.toLowerCase().includes(state.query.toLowerCase())); return `${header()}<main class="catalog-page"><div class="shell"><div class="catalog-hero"><div><div class="eyebrow green-text">Learn at your pace</div><h1>Explore courses</h1><p class="muted">Practical skills. Real instructors. A future you can build.</p></div><div class="catalog-count"><strong>${list.length}</strong><span>courses to explore</span></div></div>${state.error?`<div class="api-alert" role="alert">Unable to load courses: ${escapeHtml(state.error)} <button class="btn btn-small btn-outline" data-action="retry" data-retry="catalog">Try again</button></div>`:''}<div class="search-large"><span>${icon('search')}</span><input id="course-search" value="${state.query}" placeholder="Search for courses, skills or topics..."><button>Search</button></div><div class="catalog-layout"><aside class="filters"><div class="filter-title"><strong>Filters</strong><button data-action="clear-filters">Clear all</button></div><label>Category<select id="category-filter"><option value="">All</option>${state.categories.map(category=>`<option value="${category.id}" ${state.categoryId===category.id?'selected':''}>${escapeHtml(category.name)}</option>`).join('')}</select></label><label>Language<select id="language-filter"><option value="">All languages</option><option value="hausa" ${state.filters.language==='hausa'?'selected':''}>Hausa</option><option value="english" ${state.filters.language==='english'?'selected':''}>English</option></select></label><label>Level<select id="level-filter"><option value="">All levels</option><option value="beginner" ${state.filters.level==='beginner'?'selected':''}>Beginner</option><option value="intermediate" ${state.filters.level==='intermediate'?'selected':''}>Intermediate</option><option value="advanced" ${state.filters.level==='advanced'?'selected':''}>Advanced</option></select></label><label>Price<select id="price-filter"><option value="">Any price</option><option value="under" ${state.filters.price==='under'?'selected':''}>Under ₦10,000</option><option value="over" ${state.filters.price==='over'?'selected':''}>₦10,000+</option></select></label><div class="filter-note">🌱 <strong>Learn in Hausa</strong><small>Filter courses taught in Hausa or bilingually.</small></div></aside><section class="catalog-results"><div class="results-bar"><strong>${list.length} courses</strong><select><option>Most popular</option><option>Highest rated</option><option>Newest</option></select></div>${list.length?`<div class="course-grid">${list.map(courseCard).join('')}</div>`:'<div class="empty-state"><h3>No courses available yet.</h3><p class="muted">Try another search or check back soon.</p></div>'}</section></div></div></main>${footer()}`; }

function render() {
  let view=state.page;
  if (!canVisit(view)) {
    view = authState ? homeRouteForRole() : 'login';
    state.page = view;
  }
  const shellActive = currentRole() === 'admin' ? 'admin' : currentRole() === 'instructor' ? 'instructor' : 'dashboard';
  let html=view==='home'?home():view==='register'?auth('register'):view==='login'?auth('login'):view==='dashboard'?appShell('dashboard',loading()):view==='my-courses'?appShell('my-courses',loading()):view==='progress'?appShell('progress',loading('Loading progress...')):view==='payments'?appShell('payments',loading('Loading payment history...')):view==='catalog'?catalog():view.startsWith('course:')?`${header()}<main class="detail-page"><div class="shell">${loading('Loading course details...')}</div></main>${footer()}`:view==='instructor'?appShell('instructor',loading('Loading instructor workspace...')):view==='admin'?appShell('admin',loading('Loading administration reports...')):view.startsWith('edit-course:')?appShell('instructor',loading('Loading course editor...')):view.startsWith('checkout:')?`${header()}<main class="checkout-page"><div class="shell">${loading('Loading secure checkout...')}</div></main>${footer()}`:view.startsWith('learn:')?`<div class="learn-layout">${loading('Loading course learning...')}</div>`:appShell(shellActive,loading());
document.querySelector('#app').innerHTML=html;
bind();
window.scrollTo({top:0,behavior:'smooth'});
}
function bind() { document.querySelector('#app').innerHTML=document.querySelector('#app').innerHTML.replaceAll('CODEx Academy','Codex Cybersquad Academy').replaceAll('Flutterwave','Paystack'); document.querySelectorAll('[data-route]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); if((state.page==='login'||state.page==='register')&&el.dataset.route==='dashboard') return handleAuthSubmit(e); navigate(el.dataset.route);})); const search=document.querySelector('#course-search'); if(search) search.addEventListener('input',e=>{state.query=e.target.value; const list=catalogCourses().filter(c=>c.title.toLowerCase().includes(state.query.toLowerCase())); document.querySelector('.catalog-results').innerHTML=`<div class="results-bar"><strong>${list.length} courses</strong></div><div class="course-grid">${list.map(courseCard).join('')}</div>`;}); const select=document.querySelector('#category-filter'); if(select) select.addEventListener('change',e=>applyCategory(e.target.value)); const languageFilter=document.querySelector('#language-filter'); if(languageFilter) languageFilter.addEventListener('change',e=>{state.filters.language=e.target.value; applyCatalogFilters();}); const levelFilter=document.querySelector('#level-filter'); if(levelFilter) levelFilter.addEventListener('change',e=>{state.filters.level=e.target.value; applyCatalogFilters();}); const priceFilter=document.querySelector('#price-filter'); if(priceFilter) priceFilter.addEventListener('change',e=>{state.filters.price=e.target.value; applyCatalogFilters();});  document.querySelectorAll('[data-action="clear-filters"]').forEach(el=>el.addEventListener('click',async e=>{e.preventDefault(); state.filters={language:'',level:'',price:''}; state.query=''; state.categoryId=null; state.category='All'; await applyCatalogFilters();})); document.querySelectorAll('[data-action="pay"]').forEach(el=>el.addEventListener('click',handlePayment)); document.querySelectorAll('[data-action="complete"]').forEach(el=>el.addEventListener('click',handleComplete)); document.querySelectorAll('[data-action="flip-card"]').forEach(el=>el.addEventListener('click',flipCard)); document.querySelectorAll('[data-action="save-session"]').forEach(el=>el.addEventListener('click',saveSession)); document.querySelectorAll('[data-action="cancel-session"]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); document.querySelector('#session-form').innerHTML='';})); document.querySelectorAll('[data-action="show-session-form"]').forEach(el=>el.addEventListener('click',showSessionForm)); document.querySelectorAll('[data-action="activate-session"]').forEach(el=>el.addEventListener('click',activateSession)); document.querySelectorAll('[data-action="close-session"]').forEach(el=>el.addEventListener('click',closeSession)); document.querySelectorAll('[data-action="view-session"]').forEach(el=>el.addEventListener('click',viewSession)); document.querySelectorAll('[data-action="show-issue-form"]').forEach(el=>el.addEventListener('click',showIssueForm)); document.querySelectorAll('[data-action="save-issue"]').forEach(el=>el.addEventListener('click',saveIssue)); document.querySelectorAll('[data-action="cancel-issue"]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); document.querySelector('#issue-form').innerHTML='';})); document.querySelectorAll('[data-action="suspend-id"]').forEach(el=>el.addEventListener('click',suspendId)); document.querySelectorAll('[data-action="activate-id"]').forEach(el=>el.addEventListener('click',activateId)); document.querySelectorAll('[data-action="view-id"]').forEach(el=>el.addEventListener('click',viewId)); document.querySelectorAll('[data-action="show-category-form"]').forEach(el=>el.addEventListener('click',showCategoryForm)); document.querySelectorAll('[data-action="save-category"]').forEach(el=>el.addEventListener('click',saveCategory)); document.querySelectorAll('[data-action="start-scanner"]').forEach(el=>el.addEventListener('click',startCamera)); document.querySelectorAll('[data-action="stop-scanner"]').forEach(el=>el.addEventListener('click',stopCamera)); document.querySelectorAll('[data-action="scan-again"]').forEach(el=>el.addEventListener('click',resetScan)); document.querySelectorAll('[data-action="lesson"]').forEach(el=>el.addEventListener('click',handleLesson)); document.querySelectorAll('[data-action="submit-course"]').forEach(el=>el.addEventListener('click',handleSubmitCourse)); document.querySelectorAll('[data-action="approve-course"]').forEach(el=>el.addEventListener('click',handleApproveCourse)); document.querySelectorAll('[data-action="show-course-form"]').forEach(el=>el.addEventListener('click',showCourseForm)); document.querySelectorAll('[data-action="show-module-form"]').forEach(el=>el.addEventListener('click',showModuleForm)); document.querySelectorAll('[data-action="show-lesson-form"]').forEach(el=>el.addEventListener('click',showLessonForm)); document.querySelectorAll('[data-action="show-resource-form"]').forEach(el=>el.addEventListener('click',showResourceForm)); document.querySelectorAll('[data-action="show-category-form"]').forEach(el=>el.addEventListener('click',showCategoryForm)); document.querySelectorAll('[data-action="apply"]').forEach(el=>el.addEventListener('click',handleApplication)); document.querySelectorAll('[data-id="scan-again"]').forEach(el=>el.addEventListener('click',async e=>{e.preventDefault(); lastScannedToken=null; scanCooldown=false; if(html5QrCode&&isScanning) try{await html5QrCode.resume();}catch(e){console.error('Resume error:',e);} document.getElementById('scan-results').innerHTML='<p class="muted">Camera active. Point at a student QR code.</p>'; bind();})); document.querySelectorAll('[data-action="delete-course"],[data-action="submit-course"],[data-action="approve-course"],[data-action="reject-course"],[data-action="approve-application"],[data-action="reject-application"],[data-action="delete-module"],[data-action="delete-lesson"]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); const action=el.dataset.action; const message=action==='delete-course'||action==='delete-module'||action==='delete-lesson'?'This action cannot be undone.':action.includes('application')?'Review this instructor application?':'Confirm this course action?'; showModal('Confirm action',message,action,el.dataset.id||el.dataset.course);})); document.querySelectorAll('[data-action="edit-course"]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); navigate(`edit-course:${el.dataset.id}`);})); document.querySelectorAll('[data-action="edit-module"]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); editCurriculumItem('module',el.dataset.id);})); document.querySelectorAll('[data-action="edit-lesson"]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); editCurriculumItem('lesson',el.dataset.id);})); document.querySelectorAll('[data-action="load-editor"]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault(); navigate(`edit-course:${el.dataset.id}`);})); document.querySelectorAll('[data-action="back-instructor"]').forEach(el=>el.addEventListener('click',()=>navigate('instructor'))); document.querySelectorAll('[data-action="save-course"]').forEach(el=>el.addEventListener('click',saveCourse)); document.querySelectorAll('[data-action="show-module-form"]').forEach(el=>el.addEventListener('click',showModuleForm)); document.querySelectorAll('[data-action="show-lesson-form"]').forEach(el=>el.addEventListener('click',showLessonForm)); document.querySelectorAll('[data-action="show-resource-form"]').forEach(el=>el.addEventListener('click',showResourceForm)); document.querySelectorAll('[data-action="show-category-form"]').forEach(el=>el.addEventListener('click',showCategoryForm)); document.querySelectorAll('[data-action="close-modal"]').forEach(el=>el.addEventListener('click',()=>el.closest('.confirmation-modal')?.remove())); document.querySelectorAll('[data-action="confirm-action"]').forEach(el=>el.addEventListener('click',()=>{const modal=el.closest('.confirmation-modal'); const action=el.dataset.actionType; const id=el.dataset.id; modal?.remove(); crudAction(action,id);})); document.querySelectorAll('[data-action="retry"]').forEach(el=>el.addEventListener('click',()=>{state.page=el.dataset.retry; render(); window.__hydratePage?.();})); document.querySelectorAll('[data-action="logout"]').forEach(el=>el.addEventListener('click',async()=>{try{await api.post('/auth/logout',{});}catch(error){toast(error.message);}finally{clearAuthSession();navigate('home');}})); }
async function handleAuthSubmit(event) { event.preventDefault(); const inputs=[...document.querySelectorAll('.auth-card input')].filter(input=>input.type!=='checkbox'); const values=state.page==='register'?{full_name:inputs[0]?.value.trim(), email:inputs[1]?.value.trim(), phone:inputs[2]?.value.trim(), password:inputs[3]?.value}:{email:inputs[0]?.value.trim(), password:inputs[1]?.value}; try { const data=state.page==='register'?await api.post('/auth/register', values):await api.post('/auth/login', values); authState=data; localStorage.setItem(AUTH_KEY, JSON.stringify(data)); const current=await api.get('/auth/me'); authState.user=current.user; localStorage.setItem(AUTH_KEY, JSON.stringify(authState)); toast('Signed in successfully.'); navigate(homeRouteForRole()); } catch(error) { toast(error.message); } }
async function handleForgotPassword(event) { event.preventDefault(); const email=document.querySelector('.auth-card input[type="email"]')?.value.trim(); try { await api.post('/auth/forgot-password',{email}); toast('If the email exists, reset instructions will be sent.'); } catch(error) { toast(error.message); } }
document.addEventListener('click', event => { const authSubmit=event.target.closest('[data-action="auth-submit"]'); if(authSubmit) handleAuthSubmit(event); const forgot=event.target.closest('[data-action="forgot-password"]'); if(forgot) handleForgotPassword(event); });
async function handlePayment(event) { event.preventDefault(); if(!authState) return navigate('login'); const id=state.page.split(':')[1]; const course=catalogCourses().find(item=>String(item.id)===String(id)); if(!course) return toast('Course details are unavailable.'); try { const data=await api.post('/payments/initialize', { course_id:Number(id) }); const providerData=data.payment?.provider_data; if(providerData?.authorization_url) window.location.href=providerData.authorization_url; else toast(data.payment?.status==='successful'?'Enrollment created.':'Payment initialized. Complete payment with Paystack, then return to verify.'); } catch(error) { toast(error.message); } }
async function handleApplication(event) { event.preventDefault(); if(!authState) return navigate('login'); const form=document.querySelector('.form-panel'); const value=field=>form?.querySelector(`[data-field="${field}"]`)?.value?.trim(); try { await api.post('/instructor/apply', { phone:value('phone'), expertise:value('expertise'), experience:value('experience'), bio:value('bio') }); toast('Application submitted successfully.'); window.__hydratePage?.(); } catch(error) { toast(error.message); } }
async function handleComplete(event) { event.preventDefault(); const lessonId=event.currentTarget.dataset.lesson; try { await api.post(`/lessons/${Number(lessonId)}/progress`, { watch_time:0, completed:true }); toast('Lesson progress saved.'); } catch(error) { toast(error.message); } }
async function handleLesson(event) { event.preventDefault(); const lessonId=event.currentTarget.dataset.lesson; try { const data=await api.get(`/lessons/${Number(lessonId)}`); const lesson=data.lesson||{}; const copy=document.querySelector('.lesson-copy'); if(copy) copy.innerHTML=`<div class="eyebrow green-text">${escapeHtml(data.course?.title||'Course lesson')}</div><h1>${escapeHtml(lesson.title||'Lesson')}</h1><p>${escapeHtml(lesson.description||'Work through this lesson at your own pace.')}</p>${renderLessonVideo(lesson.video_url)}${resourcesBlock(lesson)}<div class="lesson-nav"><button class="btn btn-primary" data-action="complete" data-lesson="${lesson.id}">Mark as complete ${icon('check')}</button></div>`; bind(); } catch(error) { toast(error.message); } }
async function handleSubmitCourse(event) { event.preventDefault(); const courseId=event.currentTarget.dataset.course||event.currentTarget.dataset.id; showModal('Submit course for review?','Once submitted, administrators will review this course.','submit-course',courseId); }
async function handleApproveCourse(event) { event.preventDefault(); const courseId=event.currentTarget.dataset.course||event.currentTarget.dataset.id; showModal('Approve course?','This will publish the course for students.','approve-course',courseId); }
function showCourseForm() { const host=document.querySelector('#instructor-course-form'); if(host) host.innerHTML=courseForm({}, state.categories); bind(); }
function showSessionForm() {
  const host=document.querySelector('#session-form');
  if(!host) return;
  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const defaultStart = tomorrow.toISOString().slice(0, 16);
  host.innerHTML=`<div class="form-panel"><h2>Create Attendance Session</h2><label>Session Title<input name="title" placeholder="e.g. Web Development Workshop" required></label><label>Session Type<select name="session_type"><option value="workshop">Workshop</option><option value="class">Class</option><option value="event">Event</option><option value="seminar">Seminar</option></select></label><label>Description (optional)<textarea name="description" placeholder="Describe this session..."></textarea></label><label>Location (optional)<input name="location" placeholder="e.g. Main Hall, Room 101"></label><label>Start Time<input type="datetime-local" name="starts_at" value="${defaultStart}" required></label><label>End Time (optional)<input type="datetime-local" name="ends_at"></label><button class="btn btn-primary" data-action="save-session">Create Session</button><button class="btn btn-outline" data-action="cancel-session">Cancel</button></div>`;
  bind();
}
async function saveSession(event) {
  event.preventDefault();
  const form=document.querySelector('#session-form .form-panel');
  if(!form) return;
  const value=field=>form.querySelector(`[name="${field}"]`)?.value?.trim();
  const startsAtVal=value('starts_at');
  const endsAtVal=value('ends_at');
  const body={
    title:value('title'),
    session_type:value('session_type'),
    description:value('description')||null,
    location:value('location')||null,
    starts_at:startsAtVal?new Date(startsAtVal).toISOString():null,
    ends_at:endsAtVal?new Date(endsAtVal).toISOString():null
  };
  try {
    const endpoint=currentRole()==='admin'?'/admin/attendance/sessions':'/instructor/attendance/sessions';
    await api.post(endpoint,body);
    toast('Attendance session created successfully.');
    document.querySelector('#session-form').innerHTML='';
    if(state.page==='attendance-sessions') refreshInstructor();
    if(state.page==='all-sessions') refreshAdmin();
  } catch(error) { toast(error.message); }
}
async function activateSession(event) {
  event.preventDefault();
  const sessionId=event.currentTarget.dataset.id;
  try {
    const endpoint=currentRole()==='admin'?`/admin/attendance/sessions/${sessionId}/status`:`/instructor/attendance/sessions/${sessionId}/status`;
    await api.patch(endpoint,{status:'active'});
    toast('Session activated successfully.');
    if(state.page==='attendance-sessions') refreshInstructor();
    if(state.page==='all-sessions') refreshAdmin();
  } catch(error) { toast(error.message); }
}
async function closeSession(event) {
  event.preventDefault();
  const sessionId=event.currentTarget.dataset.id;
  try {
    const endpoint=currentRole()==='admin'?`/admin/attendance/sessions/${sessionId}/status`:`/instructor/attendance/sessions/${sessionId}/status`;
    await api.patch(endpoint,{status:'closed'});
    toast('Session closed successfully.');
    if(state.page==='attendance-sessions') refreshInstructor();
    if(state.page==='all-sessions') refreshAdmin();
  } catch(error) { toast(error.message); }
}
async function viewSession(event) {
  event.preventDefault();
  const sessionId=event.currentTarget.dataset.id;
  toast('Session details view not yet implemented.');
}
function showIssueForm() {
  const host=document.querySelector('#issue-form');
  if(!host) return;
  host.innerHTML=`<div class="form-panel"><h2>Issue Codex Student ID</h2><label>Student Email<input name="email" type="email" placeholder="student@example.com" required></label><p class="form-help">Enter the student's email address to issue a new Codex ID.</p><button class="btn btn-primary" data-action="save-issue">Issue ID</button><button class="btn btn-outline" data-action="cancel-issue">Cancel</button></div>`;
  bind();
}
async function saveIssue(event) {
  event.preventDefault();
  const form=document.querySelector('#issue-form .form-panel');
  if(!form) return;
  const email=form.querySelector('[name="email"]').value?.trim();
  if(!email) return toast('Email is required.');
  try {
    await api.post('/admin/codex-ids',{user_email:email});
    toast('Codex ID issued successfully.');
    document.querySelector('#issue-form').innerHTML='';
    refreshAdmin();
  } catch(error) { toast(error.message); }
}
async function suspendId(event) {
  event.preventDefault();
  const id=event.currentTarget.dataset.id;
  try {
    await api.patch(`/admin/codex-ids/${id}/status`,{status:'suspended'});
    toast('ID suspended successfully.');
    refreshAdmin();
  } catch(error) { toast(error.message); }
}
async function activateId(event) {
  event.preventDefault();
  const id=event.currentTarget.dataset.id;
  try {
    await api.patch(`/admin/codex-ids/${id}/status`,{status:'active'});
    toast('ID activated successfully.');
    refreshAdmin();
  } catch(error) { toast(error.message); }
}
async function viewId(event) {
  event.preventDefault();
  toast('ID details view not yet implemented.');
}
function flipCard(event) {
  event.preventDefault();
  const front=document.getElementById('id-card-front');
  const back=document.getElementById('id-card-back');
  if(front&&back){
    if(front.style.display==='none'){
      front.style.display='block';
      back.style.display='none';
    }else{
      front.style.display='none';
      back.style.display='block';
    }
  }
}
function toast(msg) {
  const conflict = typeof msg === 'string' && lastApiConflict && lastApiConflict.message === msg ? lastApiConflict : null;
  const isFailure = Boolean(conflict) || msg instanceof Error;
  const text = msg instanceof Error ? msg.message : String(msg ?? '');
  const el = document.createElement('div');
  el.className = `toast${isFailure ? ' toast-error' : ''}`;
  const action = conflict && conflict.code === 'ENROLLMENT_EXISTS'
    ? '<button class="btn btn-small btn-outline" data-toast-route="my-courses">Go to My Courses</button>'
    : '';
  el.innerHTML = `<span>${isFailure ? '!' : '✓'}</span><div class="toast-body"><p>${escapeHtml(text)}</p>${action}</div>`;
  document.body.append(el);
  el.querySelector('[data-toast-route]')?.addEventListener('click', () => {
    el.remove();
    navigate('my-courses');
  });
  lastApiConflict = null;
  setTimeout(() => el.remove(), isFailure ? 6000 : 3500);
}
function clearAuthSession() {
  authState = null;
  localStorage.removeItem(AUTH_KEY);
  inFlightGets.clear();
  state = { ...initialState(), courses: state.courses, categories: state.categories, page: 'home' };
}
async function bootstrap() { if(authState?.access_token) { try { const data=await api.get('/auth/me'); authState.user=data.user; localStorage.setItem(AUTH_KEY,JSON.stringify(authState)); } catch(error) { clearAuthSession(); } } const reference=new URLSearchParams(window.location.search).get('reference'); if(reference&&authState) { try { const data=await api.get(`/payments/verify/${encodeURIComponent(reference)}`); toast(data.payment?.status==='successful'?'Payment verified. Your course is now available.':`Payment status: ${data.payment?.status||'pending'}`); } catch(error) { toast(error.message); } } if (authState && (state.page === 'home' || state.page === 'login' || state.page === 'register') && !window.location.hash.slice(1)) { state.page = homeRouteForRole(); } render(); await Promise.all([loadCourses(),loadCategories()]); render(); hydrateForRoute(state.page); }
function setInitialRoute() {
  const route=routeFromHash();
  if(route!=='home' && canVisit(route)) state.page=route;
  else if(route!=='home') {
    state.page=authState?homeRouteForRole():'login';
    window.history.replaceState(null,'','#'+state.page);
  } else if (authState && !window.location.hash.slice(1)) {
    state.page = homeRouteForRole();
  }
}
window.addEventListener('hashchange', () => {
  const route=routeFromHash();
  if(route===state.page) {
    render();
    hydrateForRoute(route);
    return;
  }
  if(!canVisit(route)) {
    toast(authState ? 'You do not have permission to view that area.' : 'Please log in to continue.');
    state.page=authState?homeRouteForRole():'login';
    window.history.replaceState(null,'','#'+state.page);
    render();
    hydrateForRoute(state.page);
    return;
  }
  state.page=route;
  render();
  hydrateForRoute(route);
});
setInitialRoute();
bootstrap();

