from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import SignInForm, SignUpForm
from .tokens import make_login_token, read_login_token

User = get_user_model()

# We authenticate by magic link rather than via authenticate(), so we tell
# login() which backend established the session.
AUTH_BACKEND = 'django.contrib.auth.backends.ModelBackend'


def _send_magic_link(request, user):
    """Email a fresh sign-in link to the user."""
    token = make_login_token(user)
    url = request.build_absolute_uri(reverse('accounts:verify', args=[token]))
    body = render_to_string('accounts/email/magic_link.txt', {
        'user': user,
        'url': url,
        'minutes': settings.MAGIC_LINK_MAX_AGE // 60,
    })
    send_mail(
        subject='Your FlexTime sign-in link',
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def _client_ip(request):
    """The client's IP, taken straight from the connection.

    We deliberately do NOT read X-Forwarded-For: with no trusted proxy in front,
    a client can set that header freely and reset its own rate-limit counter on
    every request. If a reverse proxy that overwrites the header is ever added,
    read the forwarded IP here instead — but only because it's then trustworthy.
    """
    return request.META.get('REMOTE_ADDR', '')


def _over_rate_limit(key, limit, window):
    """Record one hit against ``key`` and return True if it now exceeds ``limit``
    within ``window`` seconds.

    ``add`` creates the counter (with its expiry) only when it's absent, so the
    window starts on the first hit and isn't pushed back by later ones.
    """
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        # The key expired between add() and incr(); count this as a fresh hit.
        cache.set(key, 1, window)
        count = 1
    return count > limit


def _safe_next(request, url):
    """Return ``url`` if it's a safe local redirect, else None."""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return None


def _rate_limited(request, email):
    """True if this email or IP has asked for too many links recently.

    Adds a flash message when it trips. Checked before creating an account or
    sending any email, so it guards both email bombing and bulk sign-ups.
    """
    limit = settings.MAGIC_LINK_RATE_LIMIT
    window = settings.MAGIC_LINK_RATE_WINDOW
    if (_over_rate_limit(f'magic-link:email:{email.lower()}', limit, window)
            or _over_rate_limit(f'magic-link:ip:{_client_ip(request)}', limit, window)):
        messages.error(
            request,
            'Too many sign-in requests. Please wait a few minutes and try again.',
        )
        return True
    return False


def _send_link_and_redirect(request, user, next_url):
    """Email the magic link, remember where to land, and show the confirmation."""
    _send_magic_link(request, user)
    request.session['link_sent_to'] = user.email
    # Where to land after sign-in (e.g. a shared calendar link the visitor
    # clicked while logged out). Carried through the email round-trip via the
    # session, since the magic link itself doesn't know about it.
    request.session['post_login_redirect'] = next_url
    return redirect('accounts:link_sent')


def sign_in(request):
    """Returning user: enter an email, get a fresh magic link."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    next_url = _safe_next(request, request.GET.get('next') or request.POST.get('next'))

    if request.method == 'POST':
        form = SignInForm(request.POST)
        if form.is_valid():
            if _rate_limited(request, form.cleaned_data['email']):
                return redirect('accounts:sign_in')
            return _send_link_and_redirect(request, form.get_user(), next_url)
    else:
        form = SignInForm()

    return render(request, 'accounts/sign_in.html', {'form': form, 'next': next_url})


def sign_up(request):
    """New user: give first name, last name, and email; the account is created
    and a magic link is emailed."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    next_url = _safe_next(request, request.GET.get('next') or request.POST.get('next'))

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            if _rate_limited(request, form.cleaned_data['email']):
                return redirect('accounts:sign_up')
            # Rate limit passed, so it's safe to create the account.
            return _send_link_and_redirect(request, form.create_user(), next_url)
    else:
        form = SignUpForm()

    return render(request, 'accounts/sign_up.html', {'form': form, 'next': next_url})


def link_sent(request):
    """Confirmation page after a magic link is emailed."""
    email = request.session.get('link_sent_to')
    return render(request, 'accounts/link_sent.html', {'email': email})


def verify(request, token):
    """Validate a magic-link token and sign the user in."""
    try:
        uid = read_login_token(token)
    except signing.SignatureExpired:
        messages.error(request, 'This sign-in link has expired. Please request a new one.')
        return redirect('accounts:sign_in')
    except signing.BadSignature:
        messages.error(request, 'This sign-in link is invalid.')
        return redirect('accounts:sign_in')

    user = User.objects.filter(pk=uid, is_active=True).first()
    if user is None:
        messages.error(request, 'This account is no longer available.')
        return redirect('accounts:sign_in')

    login(request, user, backend=AUTH_BACKEND)
    messages.success(request, f'Welcome, {user.get_short_name()}!')

    next_url = _safe_next(request, request.session.pop('post_login_redirect', None))
    return redirect(next_url or settings.LOGIN_REDIRECT_URL)


@require_POST
def sign_out(request):
    logout(request)
    messages.info(request, 'You have been signed out.')
    return redirect('accounts:sign_in')
