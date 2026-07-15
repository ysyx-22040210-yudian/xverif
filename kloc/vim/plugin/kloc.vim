" kloc Vim/gVim support.
"
" Opens source locations for L_XXXXXXXX IDs in kloc-compressed logs.
" Fixed map rule:
"   <run-dir>/sim.log
"   <run-dir>/sim.log.kloc.jsonl
"
" Optional configuration:
"   let g:kloc_repo_root = "<project-root>"
"   let g:kloc_auto_enable = 1

if exists('g:loaded_kloc_vim')
  finish
endif
let g:loaded_kloc_vim = 1

if !exists('g:kloc_auto_enable')
  let g:kloc_auto_enable = 1
endif

let s:kloc_record_cache = {}

function! s:KlocIdUnderCursor() abort
  let l:word = expand('<cWORD>')
  let l:id = matchstr(l:word, 'L_[A-Za-z0-9]\{6,32}')

  if l:id !=# ''
    return l:id
  endif

  return matchstr(getline('.'), 'L_[A-Za-z0-9]\{6,32}')
endfunction

function! s:KlocFindMapFile() abort
  let l:logfile = expand('%:p')

  if l:logfile ==# ''
    return ''
  endif

  let l:mapfile = l:logfile . '.kloc.jsonl'
  if filereadable(l:mapfile)
    return l:mapfile
  endif

  return ''
endfunction

function! s:KlocParseJsonLine(line) abort
  if a:line =~# '^\s*$'
    return {}
  endif

  if exists('*json_decode')
    try
      let l:obj = json_decode(a:line)
      if type(l:obj) == type({})
        return l:obj
      endif
    catch
    endtry
  endif

  let l:obj = {}

  let l:id = matchstr(a:line, '"loc_id"\s*:\s*"\zs[^"]\+\ze"')
  if l:id !=# ''
    let l:obj.loc_id = l:id
  endif

  let l:file = matchstr(a:line, '"file"\s*:\s*"\zs[^"]\+\ze"')
  if l:file ==# ''
    let l:file = matchstr(a:line, '"path"\s*:\s*"\zs[^"]\+\ze"')
  endif
  if l:file ==# ''
    let l:file = matchstr(a:line, '"filename"\s*:\s*"\zs[^"]\+\ze"')
  endif
  if l:file !=# ''
    let l:obj.file = l:file
  endif

  let l:line = matchstr(a:line, '"line"\s*:\s*"\zs[^"]\+\ze"')
  if l:line ==# ''
    let l:line = matchstr(a:line, '"line"\s*:\s*\zs\d\+')
  endif
  if l:line !=# ''
    let l:obj.line = l:line
  endif

  return l:obj
endfunction

function! s:KlocStripGrepPrefix(line) abort
  return substitute(a:line, '^\d\+:\ze.', '', '')
endfunction

function! s:KlocSystemList(argv) abort
  return systemlist(join(map(copy(a:argv), 'shellescape(v:val)'), ' '))
endfunction

function! s:KlocSearchLineByRg(mapfile, id) abort
  if !executable('rg')
    return ''
  endif

  let l:pattern = '"loc_id"[[:space:]]*:[[:space:]]*"' . a:id . '"'
  let l:cmd = [
        \ 'rg',
        \ '--color=never',
        \ '--no-heading',
        \ '--no-filename',
        \ '--line-number',
        \ '--max-count', '1',
        \ '--regexp', l:pattern,
        \ a:mapfile
        \ ]

  let l:out = s:KlocSystemList(l:cmd)
  if v:shell_error != 0 || empty(l:out)
    return ''
  endif

  return s:KlocStripGrepPrefix(l:out[0])
endfunction

function! s:KlocSearchLineByGrep(mapfile, id) abort
  if !executable('grep')
    return ''
  endif

  let l:pattern = '"loc_id"[[:space:]]*:[[:space:]]*"' . a:id . '"'
  let l:cmd = [
        \ 'grep',
        \ '-n',
        \ '-m', '1',
        \ '-E',
        \ l:pattern,
        \ a:mapfile
        \ ]

  let l:out = s:KlocSystemList(l:cmd)
  if v:shell_error != 0 || empty(l:out)
    return ''
  endif

  return s:KlocStripGrepPrefix(l:out[0])
endfunction

function! s:KlocSearchLineByReadfile(mapfile, id) abort
  let l:pattern = '"loc_id"\s*:\s*"' . a:id . '"'

  for l:line in readfile(a:mapfile)
    if l:line =~# l:pattern
      return l:line
    endif
  endfor

  return ''
endfunction

function! s:KlocLookupRecord(mapfile, id) abort
  let l:mapfile = fnamemodify(a:mapfile, ':p')
  let l:mtime = getftime(l:mapfile)
  let l:old = get(s:kloc_record_cache, l:mapfile, {'records': {}})

  if !has_key(s:kloc_record_cache, l:mapfile)
        \ || get(s:kloc_record_cache[l:mapfile], 'mtime', -1) != l:mtime
    let s:kloc_record_cache[l:mapfile] = {
          \ 'mtime': l:mtime,
          \ 'records': get(l:old, 'records', {})
          \ }
  endif

  let l:records = s:kloc_record_cache[l:mapfile].records
  if has_key(l:records, a:id)
    return l:records[a:id]
  endif

  let l:line = s:KlocSearchLineByRg(l:mapfile, a:id)
  if l:line ==# ''
    let l:line = s:KlocSearchLineByGrep(l:mapfile, a:id)
  endif
  if l:line ==# ''
    let l:line = s:KlocSearchLineByReadfile(l:mapfile, a:id)
  endif
  if l:line ==# ''
    return {}
  endif

  let l:rec = s:KlocParseJsonLine(l:line)
  if get(l:rec, 'loc_id', '') !=# a:id
    return {}
  endif

  let l:records[a:id] = l:rec
  return l:rec
endfunction

function! s:KlocGetFileFromRecord(rec) abort
  if has_key(a:rec, 'file')
    return a:rec.file
  endif
  if has_key(a:rec, 'path')
    return a:rec.path
  endif
  if has_key(a:rec, 'filename')
    return a:rec.filename
  endif
  return ''
endfunction

function! s:KlocLineFromRecord(rec) abort
  let l:line = get(a:rec, 'line', 1)

  if type(l:line) == type('')
    let l:line = str2nr(l:line)
  elseif type(l:line) != type(0)
    let l:line = 1
  endif

  if l:line <= 0
    let l:line = 1
  endif

  return l:line
endfunction

function! s:KlocResolvePath(file, mapfile) abort
  let l:file = a:file
  if l:file ==# ''
    return ''
  endif

  if l:file =~# '^\(/\|[A-Za-z]:[\\/]\)'
    return fnamemodify(l:file, ':p')
  endif

  let l:roots = []
  if exists('g:kloc_repo_root') && g:kloc_repo_root !=# ''
    call add(l:roots, g:kloc_repo_root)
  endif
  call add(l:roots, fnamemodify(a:mapfile, ':p:h'))
  call add(l:roots, getcwd())

  for l:root in l:roots
    let l:path = fnamemodify(l:root . '/' . l:file, ':p')
    if filereadable(l:path)
      return l:path
    endif
  endfor

  if exists('g:kloc_repo_root') && g:kloc_repo_root !=# ''
    return fnamemodify(g:kloc_repo_root . '/' . l:file, ':p')
  endif

  return fnamemodify(fnamemodify(a:mapfile, ':p:h') . '/' . l:file, ':p')
endfunction

function! s:KlocNativeGF() abort
  try
    normal! gf
  catch /^Vim\%((\a\+)\)\=:E/
    echohl WarningMsg
    echom 'kloc: native gf failed: ' . v:exception
    echohl None
  endtry
endfunction

function! KlocGF() abort
  let l:id = s:KlocIdUnderCursor()
  if l:id ==# ''
    call s:KlocNativeGF()
    return
  endif

  let l:mapfile = s:KlocFindMapFile()
  if l:mapfile ==# ''
    call s:KlocNativeGF()
    return
  endif

  let l:rec = s:KlocLookupRecord(l:mapfile, l:id)
  if empty(l:rec)
    echohl WarningMsg
    echom 'kloc: loc_id not found: ' . l:id . ' in ' . l:mapfile
    echohl None
    return
  endif

  let l:file = s:KlocGetFileFromRecord(l:rec)
  if l:file ==# ''
    echohl WarningMsg
    echom 'kloc: record has no file/path/filename field: ' . l:id
    echohl None
    return
  endif

  let l:line = s:KlocLineFromRecord(l:rec)
  let l:path = s:KlocResolvePath(l:file, l:mapfile)
  if !filereadable(l:path)
    echohl WarningMsg
    echom 'kloc: source file not readable: ' . l:path
    echohl None
    return
  endif

  execute 'edit +' . l:line . ' ' . fnameescape(l:path)
  normal! zz
endfunction

function! s:KlocMaybeMapBuffer() abort
  if !get(g:, 'kloc_auto_enable', 1)
    return
  endif

  if expand('%:e') !=# 'log'
    return
  endif

  if !filereadable(expand('%:p') . '.kloc.jsonl')
    return
  endif

  nnoremap <buffer> <silent> gf :<C-U>KlocGF<CR>
endfunction

command! KlocGF call KlocGF()

augroup kloc_gf
  autocmd!
  autocmd BufReadPost,BufNewFile *.log call s:KlocMaybeMapBuffer()
augroup END

call s:KlocMaybeMapBuffer()
