self.addEventListener('push', event => {
  let message
  try { message = event.data?.json() } catch { message = null }
  if (!message?.title) return
  event.waitUntil(self.registration.showNotification(message.title, {
    body: message.body || '', tag: `jiapu-${message.id}`, data: { url: '/#/pages/index/index?notifications=1' }
  }))
})
self.addEventListener('notificationclick', event => {
  event.notification.close()
  event.waitUntil((async () => {
    const url = new URL(event.notification.data?.url || '/', self.location.origin).href
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) { await client.navigate(url); client.postMessage({ type: 'family-notification-click' }); return client.focus() }
    }
    return self.clients.openWindow(url)
  })())
})
