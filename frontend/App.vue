<script>
import { restoreSession, startSyncWatcher, retrySync } from './utils/store.js'
import { startNotificationWatcher, refreshNotifications } from './utils/notifications.js'
export default {
  async onLaunch() { await restoreSession(); startSyncWatcher(); startNotificationWatcher() },
  onShow() { retrySync({ automatic: true }); refreshNotifications().catch(() => {}) }
}
</script>
<style>
@import './styles/icons.css';
@import './styles/parity.css';
@import './styles/parity-platform.css';
</style>
