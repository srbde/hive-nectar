import sys
from math import ceil, floor
from typing import List, Optional, Union

# Basic idea from https://github.com/kroitor/asciichart
# ╱ ╲ ╳ ─ └┲┲┲─


class AsciiChart:
    """Can be used to plot price and trade history

    :param int height: Height of the plot
    :param int width: Width of the plot
    :param int offset: Offset between tick strings and y-axis (default is 3)
    :param str placeholder: Defines how the numbers on the y-axes are formatted (default is '{:8.2f}')
    :param str charset: sets the charset for plotting, uft8 or ascii (default: utf8)
    """

    def __init__(
        self,
        height: Optional[int] = None,
        width: Optional[int] = None,
        offset: int = 3,
        placeholder: str = "{:8.2f} ",
        charset: str = "utf8",
    ) -> None:
        self.height = height
        self.width = width
        self.offset = offset
        self.placeholder = placeholder
        self.clear_data()
        if charset == "ascii" or sys.version_info[0] < 3:
            self.char_set = {
                "first_axis_elem": "|",
                "axis_elem": "|",
                "axis_elem_with_graph": "|",
                "curve_ar": "\\",
                "curve_lb": "\\",
                "curve_br": "/",
                "curve_la": "/",
                "curve_hl": "-",
                "curve_vl": "|",
                "curve_hl_dot": "-",
                "curve_vl_dot": "|",
            }
        else:
            self.char_set = {
                "first_axis_elem": "┼",
                "axis_elem": "┤",
                "axis_elem_with_graph": "┼",
                "curve_ar": "╰",
                "curve_lb": "╮",
                "curve_br": "╭",
                "curve_la": "╯",
                "curve_hl": "─",
                "curve_vl": "│",
                "curve_hl_dot": "┈",
                "curve_vl_dot": "┊",
            }

    def clear_data(self) -> None:
        """Clears all data"""
        self.canvas = []
        self.minimum = None
        self.maximum = None
        self.n = None
        self.skip = 1

    def set_parameter(
        self,
        height: Optional[int] = None,
        offset: Optional[int] = None,
        placeholder: Optional[str] = None,
    ) -> None:
        """Can be used to change parameter"""
        if height is not None:
            self.height = height
        if offset is not None:
            self.offset = offset
        if placeholder is not None:
            self.placeholder = placeholder
        self._calc_plot_parameter()

    def adapt_on_series(self, series: List[Union[int, float]]) -> None:
        """Calculates the minimum, maximum and length from the given list

        :param list series: time series to plot

        .. testcode::

            from nectar.asciichart import AsciiChart
            chart = AsciiChart()
            series = [1, 2, 3, 7, 2, -4, -2]
            chart.adapt_on_series(series)
            chart.new_chart()
            chart.add_axis()
            chart.add_curve(series)
            print(str(chart))

        """
        self.minimum = min(series)
        self.maximum = max(series)
        self.n = len(series)
        self._calc_plot_parameter()

    def _calc_plot_parameter(
        self,
        minimum: Optional[Union[int, float]] = None,
        maximum: Optional[Union[int, float]] = None,
        n: Optional[int] = None,
    ) -> None:
        """Calculates parameter from minimum, maximum and length"""
        if minimum is not None:
            self.minimum = minimum
        if maximum is not None:
            self.maximum = maximum
        if n is not None:
            self.n = n
        if self.n is None or self.maximum is None or self.minimum is None:
            return
        interval = abs(float(self.maximum) - float(self.minimum))
        if interval == 0:
            interval = 1
        if self.height is None:
            self.height = interval
        self.ratio = self.height / interval
        self.min2 = floor(float(self.minimum) * self.ratio)
        self.max2 = ceil(float(self.maximum) * self.ratio)
        if self.min2 == self.max2:
            self.max2 += 1
        intmin2 = int(self.min2)
        intmax2 = int(self.max2)
        self.rows = abs(intmax2 - intmin2)
        if self.width is not None:
            self.skip = int(self.n / self.width)
            if self.skip < 1:
                self.skip = 1
        else:
            self.skip = 1

    def plot(self, series: List[Union[int, float]], return_str: bool = False) -> Optional[str]:
        """All in one function for plotting

        .. testcode::

            from nectar.asciichart import AsciiChart
            chart = AsciiChart()
            series = [1, 2, 3, 7, 2, -4, -2]
            chart.plot(series)
        """
        self.clear_data()
        self.adapt_on_series(series)
        self.new_chart()
        self.add_axis()
        self.add_curve(series)
        if not return_str:
            print(str(self))
        else:
            return str(self)

    def new_chart(
        self,
        minimum: Optional[Union[int, float]] = None,
        maximum: Optional[Union[int, float]] = None,
        n: Optional[int] = None,
    ) -> None:
        """Clears the canvas

        .. testcode::

            from nectar.asciichart import AsciiChart
            chart = AsciiChart()
            series = [1, 2, 3, 7, 2, -4, -2]
            chart.adapt_on_series(series)
            chart.new_chart()
            chart.add_axis()
            chart.add_curve(series)
            print(str(chart))

        """
        if minimum is not None:
            self.minimum = minimum
        if maximum is not None:
            self.maximum = maximum
        if n is not None:
            self.n = n
        self._calc_plot_parameter()
        if self.n is None or self.rows is None:
            return
        self.canvas = [
            [" "] * (int(self.n / (self.skip or 1)) + self.offset) for i in range(self.rows + 1)
        ]

    def add_axis(self) -> None:
        """Adds a y-axis to the canvas

        .. testcode::

            from nectar.asciichart import AsciiChart
            chart = AsciiChart()
            series = [1, 2, 3, 7, 2, -4, -2]
            chart.adapt_on_series(series)
            chart.new_chart()
            chart.add_axis()
            chart.add_curve(series)
            print(str(chart))

        """
        # axis and labels
        if (
            self.minimum is None
            or self.maximum is None
            or self.min2 is None
            or self.max2 is None
            or self.rows is None
        ):
            # Chart was not initialized; nothing to render.
            return

        interval = abs(float(self.maximum) - float(self.minimum))
        intmin2 = int(self.min2)
        intmax2 = int(self.max2)
        for y in range(intmin2, intmax2 + 1):
            label = f"{float(self.maximum) - ((y - intmin2) * interval / self.rows)}"
            if label:
                self._set_y_axis_elem(y, label)

    def _set_y_axis_elem(self, y: Union[int, float], label: str) -> None:
        intmin2 = int(self.min2)
        y_int = int(y)
        self.canvas[y_int - intmin2][max(self.offset - len(label), 0)] = label
        if y == 0:
            self.canvas[y_int - intmin2][self.offset - 1] = self.char_set["first_axis_elem"]
        else:
            self.canvas[y_int - intmin2][self.offset - 1] = self.char_set["axis_elem"]

    def _map_y(self, y_float: Union[int, float]) -> int:
        intmin2 = int(self.min2)
        return int(round(y_float * self.ratio) - intmin2)

    def add_curve(self, series: List[Union[int, float]]) -> None:
        """Add a curve to the canvas

        :param list series: List width float data points

        .. testcode::

            from nectar.asciichart import AsciiChart
            chart = AsciiChart()
            series = [1, 2, 3, 7, 2, -4, -2]
            chart.adapt_on_series(series)
            chart.new_chart()
            chart.add_axis()
            chart.add_curve(series)
            print(str(chart))

        """
        if self.n is None:
            self.adapt_on_series(series)
        if len(self.canvas) == 0:
            self.new_chart()
        y0 = self._map_y(series[0])
        self._set_elem(y0, -1, self.char_set["axis_elem_with_graph"])
        for x in range(0, len(series[:: self.skip]) - 1):
            y0 = self._map_y(series[:: self.skip][x + 0])
            y1 = self._map_y(series[:: self.skip][x + 1])
            if y0 == y1:
                self._draw_h_line(y0, x, x + 1, line=self.char_set["curve_hl"])
            else:
                self._draw_diag(y0, y1, x)
                start = min(y0, y1) + 1
                end = max(y0, y1)
                self._draw_v_line(start, end, x, line=self.char_set["curve_vl"])

    def _draw_diag(self, y0: Union[int, float], y1: Union[int, float], x: int) -> None:
        """Plot diagonal element"""
        if y0 > y1:
            c1 = self.char_set["curve_ar"]
            c0 = self.char_set["curve_lb"]
        else:
            c1 = self.char_set["curve_br"]
            c0 = self.char_set["curve_la"]
        self._set_elem(int(y1), x, c1)
        self._set_elem(int(y0), x, c0)

    def _draw_h_line(self, y: Union[int, float], x_start: int, x_end: int, line: str = "-") -> None:
        """Plot horizontal line"""
        for x in range(x_start, x_end):
            self._set_elem(int(y), x, line)

    def _draw_v_line(self, y_start: int, y_end: int, x: int, line: str = "|") -> None:
        """Plot vertical line"""
        for y in range(y_start, y_end):
            self._set_elem(y, x, line)

    def _set_elem(self, y: int, x: int, c: str) -> None:
        """Plot signle element into canvas"""
        self.canvas[self.rows - y][x + self.offset] = c

    def __repr__(self) -> str:
        return "\n".join(["".join(row) for row in self.canvas])

    __str__ = __repr__
