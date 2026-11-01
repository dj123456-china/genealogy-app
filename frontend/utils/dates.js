import lunar from 'lunar-javascript'
const { Solar, Lunar } = lunar
export function dateString(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
export function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null
  const [y, m, d] = value.split('-').map(Number)
  const result = new Date(y, m - 1, d, 12)
  return result.getFullYear() === y && result.getMonth() === m - 1 && result.getDate() === d ? result : null
}
export function lunarDate(value) {
  const date = parseDate(value)
  if (!date) return ''
  try { const l = Solar.fromYmd(date.getFullYear(), date.getMonth() + 1, date.getDate()).getLunar(); return `农历${l.getMonthInChinese()}月${l.getDayInChinese()}` }
  catch { return '农历日期暂不可用' }
}
export function dayDistance(value, now = new Date()) {
  const target = parseDate(value)
  if (!target) return null
  return Math.round((Date.UTC(target.getFullYear(), target.getMonth(), target.getDate()) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000)
}
export function reminderCalendarFields(reminder) {
  const type = reminder.solar_term === 'qingming' ? 'qingming' : reminder.calendar_type || 'solar'
  if (!['solar', 'lunar', 'qingming'].includes(type)) throw Error('不支持的日期类型。')
  if (type !== 'lunar') return { calendar_type: type, lunar_month: null, lunar_day: null, is_leap: false }
  const source = parseDate(reminder.date)
  if (!source) throw Error('请选择农历纪念日对应的公历日期。')
  const l = Solar.fromYmd(source.getFullYear(), source.getMonth() + 1, source.getDate()).getLunar()
  return { calendar_type: 'lunar', lunar_month: Number(reminder.lunar_month) || Math.abs(l.getMonth()), lunar_day: Number(reminder.lunar_day) || l.getDay(), is_leap: reminder.is_leap ?? l.getMonth() < 0 }
}
export function occurrenceInYear(reminder, year) {
  const source = parseDate(reminder.date)
  if (!source) return ''
  if (reminder.calendar_type === 'qingming' || reminder.solar_term === 'qingming') return qingmingDate(year)
  if (reminder.calendar_type === 'lunar') {
    try {
      const fields = reminderCalendarFields(reminder)
      const l = Lunar.fromYmd(year, fields.is_leap ? -fields.lunar_month : fields.lunar_month, fields.lunar_day)
      // 非闰月年份和小月缺少三十日时不能被库滚入别的月。
      if (Math.abs(l.getMonth()) !== fields.lunar_month || l.getDay() !== fields.lunar_day || (l.getMonth() < 0) !== fields.is_leap) return ''
      return l.getSolar().toYmd()
    } catch { return '' }
  }
  const value = `${year}-${reminder.date.slice(5)}`
  return parseDate(value) ? value : ''
}
export function nextOccurrence(reminder, today = new Date()) {
  const source = parseDate(reminder.date)
  if (!source) return ''
  if (reminder.repeat !== '每年') return reminder.date
  const firstYear = Math.max(source.getFullYear() - (reminder.calendar_type === 'lunar' ? 1 : 0), today.getFullYear() - 1)
  for (let year = firstYear; year <= today.getFullYear() + 25; year++) {
    const value = occurrenceInYear(reminder, year)
    if (value && value >= reminder.date && dayDistance(value, today) >= 0) return value
  }
  return ''
}
export function countdown(value, today = new Date()) {
  const days = dayDistance(value, today)
  if (days === null) return '待下次有效日期'
  return days === 0 ? '今天' : days > 0 ? `还有 ${days} 天` : `已过 ${-days} 天`
}
export function remindersForDate(reminders, value) {
  const date = parseDate(value)
  if (!date) return []
  return reminders.filter(r => r.date === value || (r.repeat === '每年' && value >= r.date && [date.getFullYear() - 1, date.getFullYear()].some(year => occurrenceInYear(r, year) === value)))
}
export function qingmingDate(year = new Date().getFullYear()) {
  try { return Solar.fromYmd(year, 4, 5).getLunar().getJieQiTable()['清明'].toYmd() }
  catch { return '' }
}
