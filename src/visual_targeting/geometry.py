"""Explicit model pixels -> saved crop pixels -> physical desktop pixels."""
from dataclasses import dataclass
import math
import uuid

@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    width: float
    height: float
    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.left,self.top,self.width,self.height)) or self.width<=0 or self.height<=0:raise ValueError("invalid rectangle")
    def contains(self,x,y):return self.left<=x<self.left+self.width and self.top<=y<self.top+self.height
    def encloses(self,other):return self.left<=other.left and self.top<=other.top and other.left+other.width<=self.left+self.width and other.top+other.height<=self.top+self.height

@dataclass(frozen=True)
class WindowGeometry:
    hwnd: int
    client: Rect  # physical desktop pixels, not outer window/decorations
    dpi: int
    monitor: Rect
    desktop: Rect  # virtual screen, including negative origins
    revision: int = 0
    def __post_init__(self):
        if type(self.hwnd) is not int or self.hwnd<=0 or type(self.dpi) is not int or self.dpi<=0:raise ValueError("invalid window geometry")

@dataclass(frozen=True)
class Letterbox:
    crop_width: int
    crop_height: int
    model_width: int
    model_height: int
    resized_width: int
    resized_height: int
    pad_left: int
    pad_top: int
    def __post_init__(self):
        sizes=(self.crop_width,self.crop_height,self.model_width,self.model_height,self.resized_width,self.resized_height)
        if any(type(v) is not int or v<=0 for v in sizes) or any(type(v) is not int or v<0 for v in (self.pad_left,self.pad_top)) or self.pad_left+self.resized_width>self.model_width or self.pad_top+self.resized_height>self.model_height:raise ValueError("invalid letterbox")
    @classmethod
    def fit(cls,width,height,model_width,model_height):
        if min(width,height,model_width,model_height)<=0:raise ValueError("invalid input size")
        ratio=min(model_width/width,model_height/height)
        w,h=max(1,round(width*ratio)),max(1,round(height*ratio))
        return cls(width,height,model_width,model_height,w,h,(model_width-w)//2,(model_height-h)//2)
    def crop_to_model(self,x,y):
        if not Rect(0,0,self.crop_width,self.crop_height).contains(x,y):raise ValueError("crop point out of bounds")
        return x*self.resized_width/self.crop_width+self.pad_left,y*self.resized_height/self.crop_height+self.pad_top
    def model_to_crop(self,x,y):
        if not Rect(self.pad_left,self.pad_top,self.resized_width,self.resized_height).contains(x,y):raise ValueError("point lies in letterbox padding or outside model")
        return (x-self.pad_left)*self.crop_width/self.resized_width,(y-self.pad_top)*self.crop_height/self.resized_height

    def apply(self,image,value=114):
        import cv2 as cv
        if image.shape[:2]!=(self.crop_height,self.crop_width):raise ValueError("image dimensions disagree with letterbox")
        resized=cv.resize(image,(self.resized_width,self.resized_height))
        return cv.copyMakeBorder(resized,self.pad_top,self.model_height-self.resized_height-self.pad_top,
                                 self.pad_left,self.model_width-self.resized_width-self.pad_left,
                                 cv.BORDER_CONSTANT,value=(value,value,value))
    def model_box_to_crop(self,box):
        content=Rect(self.pad_left,self.pad_top,self.resized_width,self.resized_height)
        if not content.encloses(box):raise ValueError("box crosses padding or model bounds")
        sx=self.crop_width/self.resized_width;sy=self.crop_height/self.resized_height
        return Rect((box.left-self.pad_left)*sx,(box.top-self.pad_top)*sy,box.width*sx,box.height*sy)

@dataclass(frozen=True)
class Target:
    x: int
    y: int
    transform_id: str
    sequence: int
    captured_at: float
    def __post_init__(self):
        if any(type(v) is not int for v in (self.x,self.y,self.sequence)) or self.sequence<0 or not math.isfinite(self.captured_at) or self.captured_at<0:raise ValueError("invalid target provenance")

@dataclass(frozen=True)
class Transform:
    window: WindowGeometry
    crop_logical: Rect  # client-relative logical pixels at 96 DPI
    letterbox: Letterbox
    identity: str
    def __post_init__(self):
        if not Rect(0,0,self.window.client.width*96/self.window.dpi,self.window.client.height*96/self.window.dpi).encloses(self.crop_logical):raise ValueError("crop outside client")
    @property
    def desktop_crop(self):
        scale=self.window.dpi/96
        return Rect(self.window.client.left+self.crop_logical.left*scale,self.window.client.top+self.crop_logical.top*scale,self.crop_logical.width*scale,self.crop_logical.height*scale)
    def crop_to_desktop(self,x,y):
        if not Rect(0,0,self.letterbox.crop_width,self.letterbox.crop_height).contains(x,y):raise ValueError("crop point out of bounds")
        crop=self.desktop_crop
        # floor preserves half-open bounds at right/bottom; never clamp padding.
        return math.floor(crop.left+x*crop.width/self.letterbox.crop_width),math.floor(crop.top+y*crop.height/self.letterbox.crop_height)
    def desktop_to_crop(self,x,y):
        crop=self.desktop_crop
        if not crop.contains(x,y):raise ValueError("desktop point outside crop")
        return (x-crop.left)*self.letterbox.crop_width/crop.width,(y-crop.top)*self.letterbox.crop_height/crop.height
    def target(self,x,y,sequence,captured_at,*,space="model"):
        if space=="model":x,y=self.letterbox.model_to_crop(x,y)
        elif space!="crop":raise ValueError("space must be model or crop")
        dx,dy=self.crop_to_desktop(x,y)
        return Target(dx,dy,self.identity,sequence,captured_at)

    def box_to_desktop(self,box,*,space="model"):
        if space=="model":box=self.letterbox.model_box_to_crop(box)
        elif space!="crop":raise ValueError("space must be model or crop")
        if not Rect(0,0,self.letterbox.crop_width,self.letterbox.crop_height).encloses(box):raise ValueError("box outside crop")
        crop=self.desktop_crop;sx=crop.width/self.letterbox.crop_width;sy=crop.height/self.letterbox.crop_height
        return Rect(crop.left+box.left*sx,crop.top+box.top*sy,box.width*sx,box.height*sy)

class Transforms:
    def __init__(self):self.active=None;self.reason="unbound"
    def bind(self,window,crop,letterbox):
        self.active=Transform(window,crop,letterbox,uuid.uuid4().hex);self.reason="bound";return self.active
    def invalidate(self,reason):self.active=None;self.reason=reason
    def valid(self,identity,current):
        if self.active is None or self.active.identity!=identity:return False
        if self.active.window!=current:self.invalidate("window_or_display_changed");return False
        return True
