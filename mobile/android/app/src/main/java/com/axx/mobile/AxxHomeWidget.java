package com.axx.mobile;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.graphics.BitmapFactory;
import android.widget.RemoteViews;
import java.io.File;

/** A transparent home entry remains available when a launcher hides game shortcuts. */
public class AxxHomeWidget extends AppWidgetProvider {
    static RemoteViews views(Context context) {
        RemoteViews views=new RemoteViews(context.getPackageName(),R.layout.axx_home_widget);
        var icon=BitmapFactory.decodeFile(new File(context.getFilesDir(),"home-character.png").getPath());
        if(icon!=null)views.setImageViewBitmap(R.id.axx_home_image,icon);
        var open=new Intent(context,MainActivity.class).setAction(Intent.ACTION_MAIN)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        views.setOnClickPendingIntent(R.id.axx_home_root,PendingIntent.getActivity(context,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE));
        return views;
    }
    @Override public void onUpdate(Context context,AppWidgetManager manager,int[] ids) {
        for(int id:ids)manager.updateAppWidget(id,views(context));
    }
}
