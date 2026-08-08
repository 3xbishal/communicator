# Generated manually (interactive default prompt isn't available in this
# shell) — same add-then-backfill-then-tighten shape as
# 0002_message_sender_username_alter_message_sender.py.

import django.utils.timezone
from django.db import migrations, models


def backfill_local_date(apps, schema_editor):
    """
    Populate local_date for every existing message from its created_at,
    entirely in Python — reading created_at back out needs no database-side
    timezone conversion (only filtering/grouping by it does), so this is
    safe to run even on a MySQL server without timezone tables loaded,
    which is exactly the environment this field exists to work around.
    """
    Message = apps.get_model("chat", "Message")
    for message in Message.objects.all():
        local_date = django.utils.timezone.localtime(message.created_at).date()
        Message.objects.filter(pk=message.pk).update(local_date=local_date)


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_message_sender_username_alter_message_sender"),
    ]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="created_at",
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now, editable=False),
        ),
        migrations.AddField(
            model_name="message",
            name="local_date",
            field=models.DateField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_local_date, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="message",
            name="local_date",
            field=models.DateField(db_index=True, editable=False),
        ),
    ]
