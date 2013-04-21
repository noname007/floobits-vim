"""Vim specific logic"""
import os
import time

import vim

import msg
import shared as G
import utils
import protocol


class View(object):
    """editors representation of the buffer"""

    def __init__(self, vim_buf, buf):
        self.vim_buf = vim_buf
        self.buf = buf

    def __repr__(self):
        return '%s %s %s' % (self.native_id, self.buf['id'], self.buf['path'])

    def __str__(self):
        return repr(self)

    def _offset_to_vim(self, offset):
        current_offset = 0
        for line_num, line in enumerate(self.vim_buf):
            next_offset = len(line) + 1
            if current_offset + next_offset > offset:
                break
            current_offset += next_offset
        col = offset - current_offset
        return line_num + 1, col + 1

    @property
    def native_id(self):
        return self.vim_buf.number

    def is_loading(self):
        return False

    def get_text(self):
        text = '\n'.join(self.vim_buf)
        return text

    def set_text(self, text):
        # msg.debug('setting text to %s' % text.encode('utf-8').split('\n'))
        self.vim_buf[:] = text.encode('utf-8').split('\n')

    def apply_patches(self, buf, patches):
        cursor_offset = self.get_cursor_offset()
        msg.debug('cursor offset is %s bytes' % cursor_offset)

        self.set_text(patches[0])

        for patch in patches[2]:
            offset = patch[0]
            length = patch[1]
            patch_text = patch[2]
            new_offset = len(patch_text) - length
            if cursor_offset > offset:
                cursor_offset += new_offset

        self.set_cursor_position(cursor_offset)

    def focus(self):
        vim.command(':edit! %s' % self.vim_buf.name)
        vim.command(':filetype detect')

    def set_cursor_position(self, offset):
        line_num, col = self._offset_to_vim(offset)
        command = 'setpos(".", [%s, %s, %s, %s])' % (self.vim_buf.number, line_num, col, 0)
        msg.debug("setting pos: %s" % command)
        rv = int(vim.eval(command))
        if rv != 0:
            msg.debug('SHIIIIIIIIT %s' % rv)

    def get_cursor_position(self):
        """ [bufnum, lnum, col, off] """
        return vim.eval('getpos(".")')

    def get_cursor_offset(self):
        return int(vim.eval('line2byte(line("."))+col(".")')) - 2

    def get_selections(self):
        cursor = self.get_cursor_offset()
        return [[cursor, cursor]]

    def clear_selections(self):
        msg.debug('clearing selections for view %s' % self.vim_buf.name)

    def highlight(self, ranges, user_id):
        msg.debug('highlighting ranges %s' % (ranges))

    def rename(self, name):
        msg.debug('renaming %s to %s' % (self.vim_buf.name, name))


class Protocol(protocol.BaseProtocol):
    """understands vim"""
    CLIENT = 'VIM'

    def on_room_info(self, room_info):
        super(Protocol, self).on_room_info(room_info)
        vim.command(':Explore %s' % G.PROJECT_PATH)

    def maybe_selection_changed(self, vim_buf):
        buf = self.get_buf(vim_buf)
        if buf is None:
            msg.debug('no buffer found for view %s' % vim_buf.number)
            return
        view = self.get_view(buf['id'])
        msg.debug("selection changed: %s %s %s" % (vim_buf.number, buf['id'], view))
        self.SELECTION_CHANGED.append([view, False])

    def maybe_buffer_changed(self, vim_buf):
        text = vim_buf[:]
        buf = self.get_buf(vim_buf)
        if buf is None:
            msg.debug('no buffer found for view %s' % vim_buf.number)
            msg.debug('buffers:')
            for buf_id, buf in self.FLOO_BUFS.iteritems():
                msg.debug('id %s buf %s' % (buf_id, buf['path']))
            return
        if buf['buf'] != text:
            self.BUFS_CHANGED.append(buf['id'])

    def get_vim_buf_by_path(self, p):
        for vim_buf in vim.buffers:
            if vim_buf.name and p == utils.to_rel_path(vim_buf.name):
                return vim_buf
        return None

    def get_view(self, buf_id):
        buf = self.FLOO_BUFS.get(buf_id)
        if not buf:
            return None
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb:
            return View(vb, buf)
        return None

    def create_view(self, buf):
        path = self.save_buf(buf)
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb:
            return View(vb, buf)

        vim.command(':edit! %s' % path)
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb is None:
            msg.debug('vim buffer is none even though we tried to open it: %s' % path)
            return
        return View(vb, buf)

    def get_buf(self, vim_buf):
        if vim_buf.name is None:
            msg.debug('get:buf buffer has no filename')
            return None

        if not utils.is_shared(vim_buf.name):
            msg.debug('get_buf: %s is not shared' % vim_buf.name)
            return None

        rel_path = utils.to_rel_path(vim_buf.name)
        for buf_id, buf in self.FLOO_BUFS.iteritems():
            if rel_path == buf['path']:
                return buf

        msg.debug('get_buf: no buf has path %s' % rel_path)
        return None

    def save_buf(self, buf):
        path = utils.get_full_path(buf['path'])
        utils.mkdir(os.path.split(path)[0])
        with open(path, 'wb') as fd:
            fd.write(buf['buf'].encode('utf-8'))
        return path

    def delete_buf(self, buf_id):
        # TODO: somehow tell the user about this. maybe delete on disk too?
        del self.FLOO_BUFS[buf_id]

    def chat(self, username, timestamp, message, self_msg=False):
        pass
        # envelope = msg.MSG(message, timestamp, username)
        # if not self_msg:
        #     self.chat_deck.appendleft(envelope)
        # envelope.display()

    def on_msg(self, data):
        timestamp = data.get('time') or time.time()
        msg.log('[%s] <%s> %s' % (time.ctime(timestamp), data.get('username', ''), data.get('data', '')))

    def update_view(self, buf, view=None):
        msg.debug('updating view for buf %s' % buf['id'])
        view = view or self.get_view(buf['id'])
        if not view:
            msg.log('view for buf %s not found. not updating' % buf['id'])
            return

        # visible_region = view.visible_region()
        # viewport_position = view.viewport_position()
        # region = sublime.Region(0, view.size())
        # # deep copy
        # selections = [x for x in view.sel()]
        self.MODIFIED_EVENTS.put(1)
        view.set_text(buf['buf'])
        # try:
        #     edit = view.begin_edit()
        #     view.replace(edit, region, buf['buf'])
        # except Exception as e:
        #     msg.error('Exception updating view: %s' % e)
        # finally:
        #     view.end_edit(edit)
        # sublime.set_timeout(lambda: view.set_viewport_position(viewport_position, False), 0)
        # view.sel().clear()
        # view.show(visible_region, False)
        # for sel in selections:
        #     view.sel().add(sel)
        # if 'patch' in G.PERMS:
        #     view.set_read_only(False)
        # else:
        #     view.set_status('Floobits', 'You don\'t have write permission. Buffer is read-only.')
        #     view.set_read_only(True)
