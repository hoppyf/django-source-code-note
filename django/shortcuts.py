"""
This module collects helper functions and classes that "span" multiple levels
of MVC. In other words, these functions/classes introduce controlled coupling
for convenience's sake.
"""

import warnings

from django.core import urlresolvers
from django.db.models.base import ModelBase
from django.db.models.manager import Manager
from django.db.models.query import QuerySet
from django.http import (
    Http404, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect,
)
from django.template import RequestContext, loader
from django.template.context import _current_app_undefined
from django.template.engine import (
    _context_instance_undefined, _dictionary_undefined, _dirs_undefined,
)
from django.utils import six
from django.utils.deprecation import RemovedInDjango110Warning
from django.utils.encoding import force_text
from django.utils.functional import Promise


def render_to_response(template_name, context=None,  # render_to_response中比render少request参数，需要自己设置requestcontext
                       context_instance=_context_instance_undefined,
                       content_type=None, status=None, dirs=_dirs_undefined,
                       dictionary=_dictionary_undefined, using=None):
    """
    Returns a HttpResponse whose content is filled with the result of calling
    django.template.loader.render_to_string() with the passed arguments.
    """
    if (context_instance is _context_instance_undefined
            and dirs is _dirs_undefined
            and dictionary is _dictionary_undefined):
        # No deprecated arguments were passed - use the new code path
        content = loader.render_to_string(template_name, context, using=using)

    else:
        # Some deprecated arguments were passed - use the legacy code path
        content = loader.render_to_string(
            template_name, context, context_instance, dirs, dictionary,
            using=using)

    return HttpResponse(content, content_type, status)


def render(request, template_name, context=None,
           context_instance=_context_instance_undefined,
           content_type=None, status=None, current_app=_current_app_undefined,
           dirs=_dirs_undefined, dictionary=_dictionary_undefined,
           using=None):
    """
    Returns a HttpResponse whose content is filled with the result of calling
    django.template.loader.render_to_string() with the passed arguments.
    Uses a RequestContext by default.
    """
    if (context_instance is _context_instance_undefined
            and current_app is _current_app_undefined
            and dirs is _dirs_undefined
            and dictionary is _dictionary_undefined):
        # No deprecated arguments were passed - use the new code path
        # In Django 1.10, request should become a positional argument.
        content = loader.render_to_string(
            template_name, context, request=request, using=using)

    else:
        # Some deprecated arguments were passed - use the legacy code path
        if context_instance is not _context_instance_undefined:
            if current_app is not _current_app_undefined:
                raise ValueError('If you provide a context_instance you must '
                                 'set its current_app before calling render()')
        else:
            context_instance = RequestContext(request)
            if current_app is not _current_app_undefined:
                warnings.warn(
                    "The current_app argument of render is deprecated. "
                    "Set the current_app attribute of request instead.",
                    RemovedInDjango110Warning, stacklevel=2)
                request.current_app = current_app
                # Directly set the private attribute to avoid triggering the
                # warning in RequestContext.__init__.
                context_instance._current_app = current_app

        content = loader.render_to_string(
            template_name, context, context_instance, dirs, dictionary,
            using=using)

    return HttpResponse(content, content_type, status)


def redirect(to, *args, **kwargs):
    """
    Returns an HttpResponseRedirect to the appropriate URL for the arguments
    passed.

    The arguments could be:

        * A model: the model's `get_absolute_url()` function will be called.

        * A view name, possibly with arguments: `urlresolvers.reverse()` will
          be used to reverse-resolve the name.

        * A URL, which will be used as-is for the redirect location.

    By default issues a temporary redirect; pass permanent=True to issue a
    permanent redirect
    """
    if kwargs.pop('permanent', False):  # 分别表示301和302两种状态码，详见http://stackoverflow.com/questions/1393280/http-redirect-301-permanent-vs-302-temporary
        redirect_class = HttpResponsePermanentRedirect
    else:
        redirect_class = HttpResponseRedirect

    return redirect_class(resolve_url(to, *args, **kwargs))


def _get_queryset(klass):
    """
    Returns a QuerySet from a Model, Manager, or QuerySet. Created to make
    get_object_or_404 and get_list_or_404 more DRY.

    Raises a ValueError if klass is not a Model, Manager, or QuerySet.
    """
    if isinstance(klass, QuerySet):  # 是QuerySet实例直接返回
        return klass
    elif isinstance(klass, Manager):  # 是Manager返回Manager.all(),调用了manager的get_queryset()方法，也即获得QuerySet
        manager = klass
    elif isinstance(klass, ModelBase):  # 是model类则获得默认manager，然后同上
        manager = klass._default_manager
    else:
        if isinstance(klass, type):
            klass__name = klass.__name__
        else:
            klass__name = klass.__class__.__name__
        raise ValueError("Object is of type '%s', but must be a Django Model, "
                         "Manager, or QuerySet" % klass__name)
    return manager.all()


def get_object_or_404(klass, *args, **kwargs):  # 将get失败的异常转向404，比较安全的获取model实例的方法
    """
    Uses get() to return an object, or raises a Http404 exception if the object
    does not exist.

    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the get() query.

    Note: Like with get(), an MultipleObjectsReturned will be raised if more than one
    object is found.
    """
    queryset = _get_queryset(klass)
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        raise Http404('No %s matches the given query.' % queryset.model._meta.object_name)


def get_list_or_404(klass, *args, **kwargs):  # 无异常，只是将404作为空查询结果展示
    """
    Uses filter() to return a list of objects, or raise a Http404 exception if
    the list is empty.

    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the filter() query.
    """
    queryset = _get_queryset(klass)
    obj_list = list(queryset.filter(*args, **kwargs))
    if not obj_list:
        raise Http404('No %s matches the given query.' % queryset.model._meta.object_name)
    return obj_list


def resolve_url(to, *args, **kwargs):
    """
    Return a URL appropriate for the arguments passed.

    The arguments could be:

        * A model: the model's `get_absolute_url()` function will be called.

        * A view name, possibly with arguments: `urlresolvers.reverse()` will
          be used to reverse-resolve the name.

        * A URL, which will be returned as-is.
    """
    # If it's a model, use get_absolute_url()
    if hasattr(to, 'get_absolute_url'):  # 对于model对象，获取绝对路径
        return to.get_absolute_url()

    if isinstance(to, Promise):  # 用于处理类如urlparse这样的lazy实例，通过force_text()进行转换成strings
        # Expand the lazy instance, as it can cause issues when it is passed
        # further to some Python functions like urlparse.
        to = force_text(to)

    if isinstance(to, six.string_types):  # 对于string对象，以./或../开头则返回，string_types用于兼容python2和3，判断是否是str
        # Handle relative URLs
        if to.startswith(('./', '../')):
            return to

    # Next try a reverse URL resolution.  # 尝试对不满足以上条件的to进行解析，如url中命名的name
    try:
        return urlresolvers.reverse(to, args=args, kwargs=kwargs)
    except urlresolvers.NoReverseMatch:
        # If this is a callable, re-raise.
        if callable(to):
            raise
        # If this doesn't "feel" like a URL, re-raise.
        if '/' not in to and '.' not in to:
            raise

    # Finally, fall back and assume it's a URL
    return to
