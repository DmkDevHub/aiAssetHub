"""Bounded animation observations and explicitly sampled contact sheets."""
import base64
import io
from .libraries import LibraryError


def image_animation(raw,preview=False,canceled=None):
    from PIL import Image,ImageOps
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('GIF','PNG','JPEG'):raise LibraryError('UNSUPPORTED_FORMAT')
            count=getattr(image,'n_frames',1)
            if count>64 or count*image.width*image.height>32_000_000 or image.width*image.height>16_000_000:raise LibraryError('INPUT_TOO_LARGE')
            default=bool(image.info.get('default_image',False));durations=[];samples=[]
            loop=image.info.get('loop')
            channels=len(image.getbands());alpha='A' in image.getbands() or 'transparency' in image.info
            transparent=image.convert('RGBA').getchannel('A').getextrema()[0]<255
            for index in range(count):
                if canceled is not None and canceled.is_set():raise LibraryError('USER_CANCELED')
                image.seek(index);image.load()
                duration=image.info.get('duration')
                if duration is not None and (type(duration) not in (int,float) or not 0<=duration<=3600000):raise ValueError()
                if not (default and index==0):durations.append(duration)
                if preview and len(samples)<8 and not (default and index==0):
                    rgba=image.convert('RGBA');frame=Image.new('RGB',image.size,'white');frame.paste(rgba,mask=rgba.getchannel('A'))
                    samples.append(ImageOps.contain(frame,(128,128)))
            value={'format':image.format,'width':image.width,'height':image.height,
                'channels':channels,'hasAlphaChannel':alpha,'hasTransparentPixels':transparent,
                'frameCount':count-int(default),'defaultImage':default,'frameDurationsMs':durations,
                'durationSeconds':sum(durations)/1000 if all(v is not None for v in durations) else None,
                'loopCount':loop,'loopEvidence':'file-setting' if loop is not None else 'unknown',
                'fps':1000/durations[0] if durations and durations[0] and all(v==durations[0] for v in durations) else None,
                'rig':None,'rootMotion':None,'engineCompatibility':None}
            encoded=None
            if preview:
                if count-int(default)<2:raise LibraryError('UNSUPPORTED_FORMAT')
                sheet=Image.new('RGB',(512,256),'white')
                for index,frame in enumerate(samples):sheet.paste(frame,((index%4)*128,(index//4)*128))
                output=io.BytesIO();sheet.save(output,format='JPEG',quality=80)
                encoded=base64.b64encode(output.getvalue()).decode('ascii')
                value['previewFrames']=len(samples)
            return value,encoded
    except LibraryError:raise
    except Exception:raise LibraryError('INVALID_IMAGE') from None
