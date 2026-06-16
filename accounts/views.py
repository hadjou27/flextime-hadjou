from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.core import signing
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import SignInForm
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


def _safe_next(request, url):
    """Return ``url`` if it's a safe local redirect, else None."""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return None


def sign_in(request):
    """Show the sign-in/sign-up form and email a magic link on submit."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    # Where to land after sign-in (e.g. a shared calendar link the visitor
    # clicked while logged out). Carried through the email round-trip via the
    # session, since the magic link itself doesn't know about it.
    next_url = _safe_next(request, request.GET.get('next') or request.POST.get('next'))

    if request.method == 'POST':
        form = SignInForm(request.POST)
        if form.is_valid():
            user = form.get_or_create_user()
            _send_magic_link(request, user)
            request.session['link_sent_to'] = user.email
            request.session['post_login_redirect'] = next_url
            return redirect('accounts:link_sent')
    else:
        form = SignInForm()

    return render(request, 'accounts/sign_in.html', {'form': form, 'next': next_url})


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
