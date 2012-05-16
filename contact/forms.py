"""
A base contact form for allowing users to send email messages through
a web interface, and a subclass demonstrating useful functionality.

"""


from django import forms
from django.conf import settings
from django.contrib.sites.models import RequestSite, Site
from django.core.mail import EmailMessage
from django.template import loader, RequestContext
from django.utils.translation import ugettext_lazy as _


# I put this on all required fields, because it's easier to pick up
# on them with CSS or JavaScript if they have a class of "required"
# in the HTML. Your mileage may vary.
attrs_dict = { 'class': 'required' }


class ContactForm(forms.Form):
    """Basic contact form"""

    def __init__(self, data=None, files=None, request=None, *args, **kwargs):
        if request is None:
            raise TypeError("Keyword argument 'request' must be supplied")
        super(ContactForm, self).__init__(data=data, files=files, *args, **kwargs)
        self.request = request

        default_to_user = False
        if hasattr(request, 'user'):
            if callable(self.default_to_user):
                if self.default_to_user():
                    default_to_user = True
            elif self.default_to_user:
                default_to_user = True

        if default_to_user and request.user.is_authenticated():
            self.fields['name'].initial = ' '.join([request.user.first_name,
                                                   request.user.last_name])
            self.fields['email'].initial = request.user.email


    name = forms.CharField(max_length=100,
                           widget=forms.TextInput(attrs=attrs_dict),
                           label=_('Your name'))
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict,
                                                               maxlength=200)),
                             label=_('Your email address'))
    body = forms.CharField(widget=forms.Textarea(attrs=attrs_dict),
                              label=_('Your message'))

    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [mail_tuple[1] for mail_tuple in settings.MANAGERS]
    headers = None
    subject_template_name = 'contact/subject.txt'
    template_name = 'contact/body.txt'

    default_to_user = True
    set_reply_to = True

    _context = None

    def message(self):
        """Renders the body of the message to a string."""

        if callable(self.template_name):
            template_name = self.template_name()
        else:
            template_name = self.template_name
        return loader.render_to_string(template_name,
                                       self.get_context())

    def subject(self):
        """Render the subject of the message to a string."""

        subject = loader.render_to_string(self.subject_template_name,
                                          self.get_context())
        return ''.join(subject.splitlines())

    def get_context(self):
        if not self.is_valid():
            raise ValueError("Cannot generate Context from invalid contact form")
        if self._context is None:
            self._context = RequestContext(self.request,
                                           dict(self.cleaned_data,
                                                site=self.get_current_site()))
        return self._context

    def get_current_site(self):
        if Site._meta.installed:
            return Site.objects.get_current()
        elif self.request:
            return RequestSite(self.request)

    def get_message_dict(self):
        if not self.is_valid():
            raise ValueError("Message cannot be sent from invalid contact form")

        if self.headers:
            headers = dict(self.headers)
        else:
            headers = {}
        if self.set_reply_to:
            # Note that an EmailField is validated by Django.
            headers['Reply-To'] = self.cleaned_data['email']

        message_dict = {
                'from_email': self.from_email,
                'body': self.message(),
                'to': self.recipient_list,
                'subject': self.subject(),
                'headers': headers,
                }
        return message_dict

    def save(self, fail_silently=False):
        """Build and send the email message."""

        EmailMessage(**self.get_message_dict()).send(fail_silently=fail_silently)


class AkismetContactForm(ContactForm):
    """Contact form with an Akismet spam check.

    Requires the setting ``AKISMET_API_KEY``, which should be a valid
    Akismet API key.
    """
    def clean_body(self):
        if 'body' in self.cleaned_data and getattr(settings, 'AKISMET_API_KEY', ''):
            from akismet import Akismet
            from django.utils.encoding import smart_str
            akismet_api = Akismet(key=settings.AKISMET_API_KEY,
                                  blog_url='http://%s/' % self.get_current_site().domain)
            if akismet_api.verify_key():
                akismet_data = { 'comment_type': 'comment',
                                 'referer': self.request.META.get('HTTP_REFERER', ''),
                                 'user_ip': self.request.META.get('REMOTE_ADDR', ''),
                                 'user_agent': self.request.META.get('HTTP_USER_AGENT', '') }
                if akismet_api.comment_check(smart_str(self.cleaned_data['body']), data=akismet_data, build_data=True):
                    raise forms.ValidationError(_("Akismet has determined that this message is spam."))
        return self.cleaned_data['body']
