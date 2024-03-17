import uio

class TBTerm(uio.IOBase):
    def __init__( self, tft, font_regular, font_bold, rotation, bgcolor=0, fgcolor=7, readobj=None):
        try:
            self.width = tft.width()
        except:
            raise ValueError
        try:
            self.height = tft.height()
        except:
            raise ValueError

        try:
            self.fwidth = font_regular.WIDTH
            self.fheight = font_regular.HEIGHT
        except:
            pass
        try:
            self.fwidth = font_regular.MAX_WIDTH
            self.fheight = font_regular.HEIGHT
        except:
            pass
            
        self.lines_buffer = []
        self.current_line = bytearray()
        self.readobj = readobj
        self.tft = tft
        self.rotation = rotation
        self.font_regular = font_regular
        self.font_bold = font_bold
        self.bgcolor = self._xterm_color(bgcolor)
        self.bgansi = bgcolor
        self.fgcolor = self._xterm_color(fgcolor)
        self.fgansi = fgcolor
        self.initial_bgcolor = bgcolor
        self.initial_fgcolor = fgcolor
        self.font_current = font_regular
        self.cols = self.width // self.fwidth
        self.rows = self.height // self.fheight
        self.voffset = 0
        self.x = 0
        self.y = 0
        self.y_end = 0

        self.tft.init()
        self.tft.fill(self.bgcolor)
        
        # enable software scrolling on orientations that don't support hardware scrolling
        self.softscroll = self.rotation == 1 or self.rotation == 3

    def _putc(self, _c):
        c = chr(_c)
        if c == "\n":
            self._newline()
        elif c == "\x08":
            self._backspace()
        elif c >= " ":
            if self.softscroll:
                self.current_line.append(_c)
            self.tft.write( self.font_current, c, self.x * self.fwidth, self._abs2tft(self.y * self.fheight), self.fgcolor, self.bgcolor)
            self.x += 1
            if self.x >= self.cols:
                self._newline()

    def _esq_read_num(self, buf, pos):
        digit = 1
        n = 0
        while buf[pos] != 0x5B:
            n += digit * (buf[pos] - 0x30)
            pos -= 1
            digit *= 10
        return n

    def parse_ansi(self, buf, i):
        if buf[i + 1] == 0x3B or buf[i + 1] == 0x6D:  # look for ; or m
        
            if chr(buf[i-1]) in "[;": # single digit to parse
                if buf[i] == 0x30: # clear
                    self.fgcolor = self._xterm_color(self.initial_fgcolor)
                    self.fgansi = self.initial_fgcolor
                    self.bgcolor = self._xterm_color(self.initial_bgcolor)
                    self.bgansi = self.initial_bgcolor
                    self.font_current = self.font_regular
                elif buf[i] == 0x31: # bold font
                    self.font_current = self.font_bold
                elif buf[i] == 0x34: # underline
                    # TODO: not implemented
                    self.font_current = self.font_regular
                    
            elif chr(buf[i-2]) in "[;": # two digits to parse
                if buf[i - 1] == 0x33: # foreground escape code
                    if buf[i] == 0x39: # default colors
                        self.fgcolor = self._xterm_color(self.initial_fgcolor)
                        self.fgansi = self.initial_fgcolor
                    elif buf[i] == 0x38 and buf[i+1] == 0x3B and buf[i+2] == 0x35 and buf[i+3] == 0x3B: # 256 color mode
                        num = ""
                        i += 4
                        while(chr(buf[i]) not in ";m"):
                            num += chr(buf[i])
                            i += 1
                        self.fgansi = int(num)
                        self.fgcolor = self._xterm_color(self.fgansi)
                    else: # colors 0-7
                        self.fgansi = int(chr(buf[i]))
                        self.fgcolor = self._xterm_color(self.fgansi)
                elif buf[i - 1] == 0x39: # foreground escape code, colors 8-15
                    self.fgansi = int(chr(buf[i]))+8
                    self.fgcolor = self._xterm_color(self.fgansi)
                    
                elif buf[i - 1] == 0x34: # background escape code
                    if buf[i] == 0x39: # default colors
                        self.bgcolor = self._xterm_color(self.initial_bgcolor)
                        self.bgansi = self.initial_bgcolor
                    elif buf[i] == 0x38 and buf[i+1] == 0x3B and buf[i+2] == 0x35 and buf[i+3] == 0x3B: # 256 color mode
                        num = ""
                        i += 4
                        while(chr(buf[i]) not in ";m"):
                            num += chr(buf[i])
                            i += 1
                        self.bgansi = int(num)
                        self.bgcolor = self._xterm_color(self.bgansi)
                    else: # colors 0-7
                        self.bgansi = int(chr(buf[i]))
                        self.bgcolor = self._xterm_color(self.bgansi)
                        
            elif chr(buf[i-3]) in "[;": # 3 digits to parse
                if buf[i-2] == 0x31 and buf[i-1] == 0x30: # background escape code, colors 8-15
                    self.bgansi = int(chr(buf[i]))+8
                    self.bgcolor = self._xterm_color(self.bgansi)

    def write(self, buf):
        self._draw_cursor(self.initial_bgcolor)
        i = 0
        
        while i < len(buf):
            c = buf[i]

            if c == 0x1B:
                i += 1
                esc = i
                
                if self.softscroll:
                    self.current_line.append(c)

                while chr(buf[i]) in "[;0123456789":
                    self.parse_ansi(buf, i)
                    if self.softscroll:
                        self.current_line.append(buf[i])
                    i += 1
                    
                c = buf[i]

                if self.softscroll:
                    self.current_line.append(c)
                        
                if c == 0x4B and i == esc + 1:  # ESC [ K
                    self._clear_cursor_eol()
                elif c == 0x44:  # ESC [ n D
                    for _ in range(self._esq_read_num(buf, i - 1)):
                        self._backspace()
            else:
                self._putc(c)
            i += 1
        self._draw_cursor(self.fgcolor)

        return len(buf)

    def write_line(self, buf, y):
        i = 0
        x = 0

        while i < len(buf):
            if buf[i] == 0x1B:
                i += 1

                while chr(buf[i]) in "[;0123456789":
                    self.parse_ansi(buf, i)
                    i += 1
            else:
                self.tft.write(self.font_current, chr(buf[i]), x * self.fwidth, y * self.fheight, self.fgcolor, self.bgcolor)
                x += 1
            i += 1

    def readinto(self, buf, nbytes=0):
        if self.readobj != None:
            return self.readobj.readinto(buf, nbytes)
        else:
            return None

    def _abs2tft(self, v):
        return (self.voffset + v) % self.height

    def _newline(self):
        if self.softscroll:
            self.lines_buffer.append(self.current_line)
            self.current_line = bytearray()

        self.x = 0
        self.y += 1
        if self.y >= self.rows:
            if self.softscroll:
                # software scrolling based on buffered lines
                self._fill_rect(0, 0, self.width, self.height, self.bgcolor)
                y = 0
                self.lines_buffer = self.lines_buffer[-(self.height // self.fheight) + 1:]
                for line in self.lines_buffer:
                    self.write_line(line, y)
                    y += 1
                self.y = self.rows - 1
            else:
                # hardware scrolling
                self.voffset = ( self.voffset - -self.fheight + self.height) % self.height
                if self.rotation == 0:
                    self.tft.vscsad(self.voffset)
                elif self.rotation == 2:
                    self.tft.vscsad(self.height - self.voffset)
                self._fill_rect( 0, self.height - self.fheight, self.width, self.fheight, self.bgcolor)
                self.y = self.rows - 1
        self.y_end = self.y

        # TODO: remove redundancy in this block; there's no need to copy the codes each line
        if self.softscroll:
            self.current_line.append(0x1B) # \033
            self.current_line.append(0x5B) # [
            
            if self.bgansi >= 8:
                self.current_line.append(0x31) # 1
                self.current_line.append(0x30) # 0
            else:
                self.current_line.append(0x34) # 4
            self.current_line.append(self._int_to_hex(self.bgansi))
            self.current_line.append(0x3B) # ;
            
            if self.fgansi >= 8:
                self.current_line.append(0x33) # 9
            else:
                self.current_line.append(0x33) # 3
            self.current_line.append(self._int_to_hex(self.fgansi))
            self.current_line.append(0x3B) # ;
            
            if self.font_current == self.font_regular:
                self.current_line.append(0x30) # 0
                self.current_line.append(0x6D) # m
            elif self.font_current == self.font_bold:
                self.current_line.append(0x31) # 1
                self.current_line.append(0x6D) # m

    def _int_to_hex(self, integer):
        hexa = 0x00
        istr = str(integer)
        i = len(istr) -1
        for c in istr:
            hexa += ord(c) << (i*8)
            i -= 1
        return hexa

    def _backspace(self):
        if self.x == 0:
            if self.y > 0:
                self.y -= 1
                self.x = self.cols - 1
        else:
            self.x -= 1
        self._fill_rect( self.x * self.fwidth, self.y * self.fheight, self.fwidth, self.fheight, self.bgcolor)

    def _clear_cursor_eol(self):
        self._fill_rect( self.x * self.fwidth, self.y * self.fheight, self.width, self.fheight, self.bgcolor)
        for l in range(self.y + 1, self.y_end + 1):
            self._fill_rect(0, l * self.fheight, self.width, self.fheight, self.bgcolor)
        self.y_end = self.y

    def _draw_cursor(self, color):
        self.tft.vline( self.x * self.fwidth, self._abs2tft(self.y * self.fheight), self.fheight, color)

    def _fill_rect(self, x, y, w, h, color):
        top = self._abs2tft(y)
        bottom = self._abs2tft(y + h)
        if bottom > top:
            self.tft.fill_rect(x, top, w, h, color)
        else:
            self.tft.fill_rect(x, top, w, self.height - top, color)
            self.tft.fill_rect(x, 0, w, bottom, color)

    # returns an RGB565 color based on the ansi number
    def _xterm_color(self, number):
        if number < 16:
            if number == 0:
                return 0x0000
            elif number == 1:
                return 0x8000
            elif number == 2:
                return 0x0400
            elif number == 3:
                return 0x8400
            elif number == 4:
                return 0x0010
            elif number == 5:
                return 0x8010
            elif number == 6:
                return 0x0410
            elif number == 7:
                return 0xbdf7
            elif number == 8:
                return 0x8410
            elif number == 9:
                return 0xf800
            elif number == 10:
                return 0x7e0
            elif number == 11:
                return 0xffe0
            elif number == 12:
                return 0x001f
            elif number == 13:
                return 0xf81f
            elif number == 14:
                return 0x07ff
            elif number == 15:
                return 0xffff
                
        elif number < 231:
            # TODO colors seems a bit off
            index_R = ((number - 16) // 36)
            index_G = (((number - 16) % 36) // 6)
            index_B = ((number - 16) % 6)
            rgb_R = round((55+index_R * 40) / 255 * 31) if index_R > 0 else 0
            rgb_G = round((55+index_G * 40) / 255 * 63) if index_G > 0 else 0
            rgb_B = round((55+index_B * 40) / 255 * 31) if index_B > 0 else 0
            return (rgb_R << 11) | (rgb_G << 5) | rgb_B
            
        else:
            gray = (number - 232) * 10 + 8
            rb = round(gray / 255 * 31)
            g = round(gray / 255 * 63)
            return (rb << 11 ) | (g << 5) | rb

