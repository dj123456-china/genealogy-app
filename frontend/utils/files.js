export async function chooseJsonFile() {
  // #ifdef H5
  if (typeof document !== 'undefined') {
    return new Promise((resolve, reject) => {
      const input = document.createElement('input'); input.type = 'file'; input.accept = '.json,application/json'
      input.oncancel = () => { input.remove(); resolve(null) }
      input.onchange = async () => { try { const file = input.files?.[0]; if (!file) return resolve(null); if (file.size > 15 * 1024 * 1024) throw Error('备份文件不能超过15MB。'); resolve(JSON.parse(await file.text())) } catch { reject(Error('无法读取备份，请选择有效的 JSON 家谱文件。')) } finally { input.remove() } }
      input.hidden = true; document.body.appendChild(input); input.click()
    })
  }
  // #endif
  return new Promise((resolve, reject) => {
    const choose = uni.chooseMessageFile || uni.chooseFile
    if (!choose) return reject(Error('当前平台不支持选择文件，请使用下方备份文本导入。'))
    choose({ count: 1, type: 'file', extension: ['json'], success: r => {
      const path = r.tempFiles?.[0]?.path
      const fs = uni.getFileSystemManager?.()
      if (!fs) return reject(Error('当前平台请使用备份文本导入。'))
      fs.readFile({ filePath: path, encoding: 'utf8', success: value => { try { resolve(JSON.parse(value.data)) } catch { reject(Error('备份文件格式无效。')) } }, fail: reject })
    }, fail: e => /cancel/.test(e.errMsg || '') ? resolve(null) : reject(Error('文件选择失败。')) })
  })
}
export async function downloadJson(data) {
  const content = JSON.stringify(data, null, 2), name = `家谱备份-${new Date().toISOString().replace(/[.:]/g, '-')}.json`
  // #ifdef H5
  if (typeof document !== 'undefined') {
    const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
    const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    return { downloaded: true, content }
  }
  // #endif
  if (typeof plus !== 'undefined') {
    const path = await new Promise((resolve, reject) => plus.io.requestFileSystem(plus.io.PRIVATE_DOC, fs => fs.root.getFile(name, { create: true }, entry => entry.createWriter(writer => { writer.onwrite = () => resolve(entry.toLocalURL()); writer.onerror = reject; writer.write(content) }, reject), reject), reject))
    return { downloaded: true, path, content }
  }
  const fs = uni.getFileSystemManager?.()
  const root = typeof wx !== 'undefined' ? wx.env.USER_DATA_PATH : null
  if (fs && root) {
    const path = `${root}/${name}`
    await new Promise((resolve, reject) => fs.writeFile({ filePath: path, data: content, encoding: 'utf8', success: resolve, fail: reject }))
    return { downloaded: true, path, content }
  }
  return { downloaded: false, content }
}
