from django.db import connections
from django.test.runner import DiscoverRunner


class Runner(DiscoverRunner):
    """Drop the test database even if a background task (a collab room's flush, say) still holds a connection.

    Those connections belong to worker threads that outlive the test that started them; without this, DROP
    DATABASE can fail with "being accessed by other users" and leave a stale database behind.
    """

    def teardown_databases(self, old_config, **kwargs):
        for conn in connections.all():
            if conn.vendor != 'postgresql':
                continue
            name = conn.settings_dict['NAME']
            conn.close()
            with conn._nodb_cursor() as cursor:
                cursor.execute(
                    'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()',
                    [name])
        super().teardown_databases(old_config, **kwargs)
