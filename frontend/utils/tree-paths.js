import { demoMembers, demoEdges } from './parity-domain.js'
import { familyEdges } from './family.js'

// A path always comes from recorded member IDs. Names are only presentation labels.
export function relationshipPaths(boxes, members = demoMembers, edges = null) {
  const lookup = new Map(members.map(member => [String(member.id), member]))
  const byName = new Map(members.map(member => [member.name, member]))
  const source = edges || (members === demoMembers ? demoEdges : familyEdges(members))
  const normalized = source.map(edge => ({
    from: String(edge.from || byName.get(edge.parent || edge.a)?.id || ''),
    to: String(edge.to || byName.get(edge.child || edge.b)?.id || ''),
    kind: edge.kind || 'parent'
  }))
  const boxFor = id => boxes[id] || boxes[lookup.get(id)?.name]
  return normalized.filter(edge => boxFor(edge.from) && boxFor(edge.to)).map((edge, index) => {
    const first = boxFor(edge.from), second = boxFor(edge.to)
    const a = lookup.get(edge.from), b = lookup.get(edge.to)
    let d, x, y
    let label = edge.kind === 'spouse' ? '配偶' : edge.kind === 'sibling' ? '同辈' : a?.gender === '男' ? (b?.gender === '男'?'父子':b?.gender === '女'?'父女':'亲子') : a?.gender === '女' ? (b?.gender === '男'?'母子':b?.gender === '女'?'母女':'亲子') : '亲子'
    if (edge.kind === 'spouse' || edge.kind === 'sibling') {
      const left = first.centerX <= second.centerX ? first : second, right = left === first ? second : first
      if (Math.abs(first.centerY - second.centerY) < 8) {
        x = (left.right + right.left) / 2; y = left.centerY
        d = `M ${left.right} ${left.centerY} H ${right.left}`
      } else {
        // Explicit generation fields can place spouses on separate rows.
        x = Math.max(first.right, second.right) + 24 + index % 3 * 12
        y = (first.centerY + second.centerY) / 2
        d = `M ${first.right} ${first.centerY} C ${x} ${first.centerY} ${x} ${second.centerY} ${second.right} ${second.centerY}`
      }
    } else if (second.top > first.bottom) {
      const peers = normalized.filter(item => item.kind === 'parent' && item.to === edge.to).sort((u,v) => boxFor(u.from)?.centerX - boxFor(v.from)?.centerX)
      const offset = (peers.indexOf(edge) - (peers.length - 1) / 2) * 24
      const endX = second.centerX + offset, lane = (first.bottom + second.top) / 2
      x = endX; y = second.top - 28 - peers.indexOf(edge) * 24
      d = `M ${first.centerX} ${first.bottom} C ${first.centerX} ${lane} ${endX} ${lane} ${endX} ${second.top}`
    } else {
      // Retain visibility even when a manually entered generation contradicts the edge.
      x = Math.max(first.right, second.right) + 28 + index % 4 * 12
      y = (first.centerY + second.centerY) / 2
      d = `M ${first.right} ${first.centerY} C ${x} ${first.centerY} ${x} ${second.centerY} ${second.right} ${second.centerY}`
    }
    return { d, kind: edge.kind, x, y, label, description: `${a?.name || edge.from}与${b?.name || edge.to}：${label}` }
  })
}
