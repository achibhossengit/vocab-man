from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField("email address", unique=True)
    daily_word_limit = models.PositiveSmallIntegerField(
        default=10,
        help_text="Distinct words this account may send to the model per UTC day.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class WordLan(models.TextChoices):
    EN = "en", "English"
    BN = "bn", "Bangla"
    AR = "ar", "Arabic"


class WordProfile(models.Model):
    Lan = WordLan

    lan = models.CharField(max_length=16, choices=Lan.choices)
    word = models.CharField(max_length=255)
    pos = models.CharField(max_length=64)
    definition = models.TextField()
    example = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("lan"),
                models.functions.Lower("word"),
                models.functions.Lower("pos"),
                name="unique_word_profile_lan_word_pos",
            ),
            models.CheckConstraint(
                condition=models.Q(lan__in=WordLan.values),
                name="word_profile_lan_known",
            ),
        ]
        indexes = [
            models.Index(fields=["lan", "word"], name="word_profile_lan_word"),
        ]

    def save(self, *args, **kwargs):
        self.lan = self.lan.strip().lower()
        self.word = " ".join(self.word.split())
        self.pos = " ".join(self.pos.split())
        if self.pos.isascii():
            self.pos = self.pos.lower()
        self.definition = " ".join(self.definition.split())
        self.example = " ".join(self.example.split())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.word} ({self.lan}, {self.pos})"


class WordRelation(models.Model):
    class Kind(models.TextChoices):
        SYNONYM = "syn", "synonym"
        ANTONYM = "ant", "antonym"

    source = models.ForeignKey(
        WordProfile,
        on_delete=models.CASCADE,
        related_name="relations_as_source",
    )
    target = models.ForeignKey(
        WordProfile,
        on_delete=models.CASCADE,
        related_name="relations_as_target",
    )
    relation = models.CharField(max_length=16, choices=Kind.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "relation"],
                name="unique_word_relation",
            ),
            models.CheckConstraint(
                condition=models.Q(source__lt=models.F("target")),
                name="word_relation_source_before_target",
            ),
        ]
        indexes = [
            models.Index(fields=["target", "relation"], name="word_relation_target"),
        ]

    def save(self, *args, **kwargs):
        if self.source_id and self.target_id and self.source_id > self.target_id:
            self.source_id, self.target_id = self.target_id, self.source_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.source_id} {self.relation} {self.target_id}"
