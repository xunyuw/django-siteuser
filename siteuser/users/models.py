# -*- coding: utf-8 -*-
import os
import time
import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string

from siteuser.settings import (
    MAX_EMAIL_LENGTH,
    MAX_USERNAME_LENGTH,
    AVATAR_URL_PREFIX,
    DEFAULT_AVATAR,
    AVATAR_DIR,
)

from siteuser.upload_avatar.signals import avatar_crop_done


class SiteUserManager(models.Manager):
    def create(self, is_social, **kwargs):
        if 'user' not in kwargs and 'user_id' not in kwargs:
            siteuser_kwargs = {
                'is_social': is_social,
                'username': kwargs.pop('username'),
                'date_joined': timezone.now(),
            }
            if 'avatar_url' in kwargs:
                siteuser_kwargs['avatar_url'] = kwargs.pop('avatar_url')
            user = SiteUser.objects.create(**siteuser_kwargs)
            kwargs['user_id'] = user.id

        return super(SiteUserManager, self).create(**kwargs)


class SocialUserManager(SiteUserManager):
    def create(self, **kwargs):
        return super(SocialUserManager, self).create(True, **kwargs)


class InnerUserManager(SiteUserManager):
    def create(self, **kwargs):
        return super(InnerUserManager, self).create(False, **kwargs)


class SocialUser(models.Model):
    """第三方帐号"""
    user = models.OneToOneField('SiteUser', related_name='social_user')
    site_uid = models.CharField(max_length=128)
    site_name = models.CharField(max_length=32)

    objects = SocialUserManager()

    class Meta:
        unique_together = (('site_uid', 'site_name'),)


class InnerUser(models.Model):
    """自身注册用户"""
    user = models.OneToOneField('SiteUser', related_name='inner_user')
    email = models.CharField(max_length=MAX_EMAIL_LENGTH, unique=True)
    passwd = models.CharField(max_length=40)
    token = models.CharField(max_length=40, blank=True)

    objects = InnerUserManager()
    
    def generate_token(self):
        key = '{0}{1}'.format(get_random_string(), time.time())
        token = hashlib.sha1(key).hexdegist()
        self.token = token
        return token



def _siteuser_extend():
    siteuser_extend_model = getattr(settings, 'SITEUSER_EXTEND_MODEL', None)
    if not siteuser_extend_model:
        return models.Model

    if isinstance(siteuser_extend_model, models.base.ModelBase):
        # 直接定义的 SITEUSER_EXTEND_MODEL
        if not siteuser_extend_model._meta.abstract:
            raise AttributeError("%s must be an abstract model" % siteuser_extend_model)
        return siteuser_extend_model

    # 以string的方式定义的 SITEUSER_EXTEND_MODEL
    _module, _model = siteuser_extend_model.rsplit('.', 1)
    try:
        m = __import__(_module, fromlist=['.'])
        _model = getattr(m, _model)
    except:
        m = __import__(_module + '.models', fromlist=['.'])
        _model = getattr(m, _model)
    
    if not _model._meta.abstract:
        raise AttributeError("%s must be an abstract model" % siteuser_extend_model)
    return _model



class SiteUser(_siteuser_extend()):
    """用户信息，如果需要（大部分情况也确实是需要）扩展SiteUser的字段，
    需要定义SITEUSER_EXTEND_MODEL.此model必须设置 abstract=True
    """
    is_social = models.BooleanField()
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField()

    username = models.CharField(max_length=MAX_USERNAME_LENGTH, db_index=True)
    # avatar_url for social user
    avatar_url = models.CharField(max_length=255, blank=True)
    # avatar_name for inner user uploaded avatar
    avatar_name = models.CharField(max_length=64, blank=True)

    def __unicode__(self):
        return u'<SiteUser %d>' % self.id

    @property
    def avatar(self):
        if not self.avatar_url and not self.avatar_name:
            return AVATAR_URL_PREFIX + DEFAULT_AVATAR
        if self.is_social:
            return self.avatar_url
        return AVATAR_URL_PREFIX + self.avatar_name


def _save_avatar_in_db(sender, uid, avatar_name, **kwargs):
    if not SiteUser.objects.filter(id=uid, is_social=False).exists():
        return

    old_avatar_name = SiteUser.objects.get(id=uid).avatar_name
    if old_avatar_name:
        _path = os.path.join(AVATAR_DIR, old_avatar_name)
        try:
            os.unlink(_path)
        except:
            pass

    SiteUser.objects.filter(id=uid).update(avatar_name=avatar_name)


avatar_crop_done.connect(_save_avatar_in_db)

